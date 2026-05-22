"""executor 노드 — sandbox 실행 + symbolic verifier dispatch (D안 PR-A3).

LLM 없음 (deterministic).
v0 의 sandbox 4-tier (Docker/sandboxexec/RLIMIT) 재사용 — generic infra.

핵심 책임:
1. ``attempt.code`` 를 각 sample 별로 sandboxed Python 실행 → SampleResult list
2. ``get_verifier(target_algorithm)`` dispatch → InvariantViolation list (PR-A2)
3. ``samples_engaged = verifier.count_engaged_samples(spec)`` (H1 측정 신호)
4. failure_mode 분류 + StructuredFeedback 생성 (target_node enum 결정)
5. VerificationResult 반환
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ipe.sandbox.runner import RunResult, RunSpec, SandboxedRunner
from ipe.sandbox.selector import pick_runner

from ..schema import (
    FailureMode,
    InvariantViolation,
    ProblemSpec,
    SampleResult,
    SolutionAttempt,
    StructuredFeedback,
    TargetAlgorithm,
    TargetNode,
    VerificationResult,
)
from ..state import V1State
from ..verifiers import SymbolicVerifier, get_verifier


class ExecutorRunner(Protocol):
    """v0 SandboxedRunner 인터페이스 sub-set — test 가 mock 주입."""

    def run(self, spec: RunSpec) -> RunResult: ...


def _execute_one_sample(
    runner: ExecutorRunner,
    code: str,
    stdin: str,
    time_limit_ms: int,
    memory_limit_mb: int,
) -> RunResult:
    """workdir 에 solution.py write + sandbox 실행."""
    with tempfile.TemporaryDirectory() as wd:
        (Path(wd) / "solution.py").write_text(code, encoding="utf-8")
        spec = RunSpec(
            cmd=["python3", "solution.py"],
            cwd=wd,
            stdin=stdin,
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )
        return runner.run(spec)


def _to_sample_result(
    idx: int,
    expected: str,
    run_result: RunResult,
) -> SampleResult:
    actual = run_result.stdout.strip() if run_result.status == "OK" else ""
    passed = run_result.status == "OK" and actual == expected.strip()
    return SampleResult(
        index=idx,
        passed=passed,
        expected_output=expected,
        actual_output=actual,
        stderr=run_result.stderr[:1000],
        elapsed_ms=run_result.elapsed_ms,
    )


def _classify_run_failure(
    sample_results: list[SampleResult],
    run_statuses: list[str],
) -> tuple[FailureMode, str, str] | None:
    """sample 실행 단계의 실패 분류. 없으면 None (verifier 단계로 진입).

    Returns: (failure_mode, actionable_hint, blocking_signature).
    Phase 1 priority: CRASH > TIMEOUT > MISMATCH.
    """
    for i, status in enumerate(run_statuses):
        if status in {"RTE", "SANDBOX_ERROR"}:
            sr = sample_results[i]
            return (
                FailureMode.SAMPLE_CRASH,
                f"sample {i} crashed (status={status}). stderr: {sr.stderr[:200]}",
                f"sample-{i}-crash",
            )
    for i, status in enumerate(run_statuses):
        if status == "TLE":
            return (
                FailureMode.SAMPLE_TIMEOUT,
                f"sample {i} exceeded time limit (status=TLE)",
                f"sample-{i}-timeout",
            )
        if status in {"MLE", "OLE"}:
            return (
                FailureMode.SAMPLE_TIMEOUT,
                f"sample {i} exceeded resource limit (status={status})",
                f"sample-{i}-{status.lower()}",
            )
    for i, sr in enumerate(sample_results):
        if not sr.passed:
            return (
                FailureMode.SAMPLE_MISMATCH,
                (
                    f"sample {i}: expected {sr.expected_output!r}, "
                    f"got {sr.actual_output!r}"
                ),
                f"sample-{i}-mismatch",
            )
    return None


def _build_verification(
    *,
    iteration: int,
    sample_results: list[SampleResult],
    run_statuses: list[str],
    violations: list[InvariantViolation],
    samples_engaged: int,
) -> VerificationResult:
    """우선순위: run failure > invariant violation > pass.

    Phase 1: target_node 는 항상 CODER (architect/designer escalation 은 Phase 2).
    """
    sample_failure = _classify_run_failure(sample_results, run_statuses)
    if sample_failure is not None:
        mode, hint, sig = sample_failure
        return VerificationResult(
            overall_pass=False,
            failure_mode=mode,
            sample_results=sample_results,
            invariant_violations=violations,
            feedback=StructuredFeedback(
                target_node=TargetNode.CODER,
                actionable_hint=hint,
                blocking_signature=sig,
            ),
            iteration=iteration,
            samples_engaged=samples_engaged,
        )
    if violations:
        first = violations[0]
        return VerificationResult(
            overall_pass=False,
            failure_mode=FailureMode.INVARIANT_VIOLATION,
            sample_results=sample_results,
            invariant_violations=violations,
            feedback=StructuredFeedback(
                target_node=TargetNode.CODER,
                actionable_hint=first.description,
                blocking_signature=f"{first.invariant_kind}-violated",
            ),
            iteration=iteration,
            samples_engaged=samples_engaged,
        )
    return VerificationResult(
        overall_pass=True,
        failure_mode=FailureMode.NONE,
        sample_results=sample_results,
        invariant_violations=[],
        feedback=None,
        iteration=iteration,
        samples_engaged=samples_engaged,
    )


VerifierGetter = Callable[[TargetAlgorithm], SymbolicVerifier | None]


def make_executor_node(
    *,
    runner: ExecutorRunner | None = None,
    verifier_getter: VerifierGetter = get_verifier,
) -> Callable[[V1State], V1State]:
    """factory — graph build 시 호출. test 는 mock runner + mock getter 주입."""
    resolved_runner: ExecutorRunner = runner if runner is not None else _default_runner()

    def node(state: V1State) -> V1State:
        spec, attempt = _require(state)
        sample_results, run_statuses = _run_all_samples(spec, attempt, resolved_runner)
        verifier = verifier_getter(state.target_algorithm)
        violations: list[InvariantViolation] = []
        samples_engaged = 0
        if verifier is not None:
            outputs = [sr.actual_output for sr in sample_results]
            if state.design is not None:
                violations = list(
                    verifier.verify(
                        spec=spec,
                        design=state.design,
                        attempt=attempt,
                        sample_outputs=outputs,
                    )
                )
            samples_engaged = verifier.count_engaged_samples(spec)
        verification = _build_verification(
            iteration=state.iteration,
            sample_results=sample_results,
            run_statuses=run_statuses,
            violations=violations,
            samples_engaged=samples_engaged,
        )
        return state.model_copy(update={"verification": verification})

    return node


def _default_runner() -> SandboxedRunner:
    return pick_runner()


def _require(state: V1State) -> tuple[ProblemSpec, SolutionAttempt]:
    if state.spec is None or state.attempt is None:
        msg = "executor requires state.spec and state.attempt"
        raise ValueError(msg)
    return state.spec, state.attempt


def _run_all_samples(
    spec: ProblemSpec, attempt: SolutionAttempt, runner: ExecutorRunner
) -> tuple[list[SampleResult], list[str]]:
    sample_results: list[SampleResult] = []
    run_statuses: list[str] = []
    for i, sample in enumerate(spec.sample_testcases):
        result = _execute_one_sample(
            runner=runner,
            code=attempt.code,
            stdin=sample.input_text,
            time_limit_ms=spec.time_limit_ms,
            memory_limit_mb=spec.memory_limit_mb,
        )
        sample_results.append(_to_sample_result(i, sample.expected_output, result))
        run_statuses.append(result.status)
    return sample_results, run_statuses
