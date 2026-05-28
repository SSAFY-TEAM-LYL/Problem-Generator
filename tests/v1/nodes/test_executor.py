"""executor 노드 단위 테스트 — mock runner + mock verifier."""

from __future__ import annotations

from typing import Any

import pytest

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.nodes.executor import make_executor_node
from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    FailureMode,
    InvariantViolation,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    TargetAlgorithm,
    TargetNode,
)
from ipe.v1.state import V1State, initial_state


def _spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="t",
        description="d",
        io_contract=IOContract(input_format="V E s t...", output_format="int"),
        sample_testcases=[
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
            SampleTestCase(input_text="3 2 0 2\n0 1 1\n1 2 2", expected_output="3"),
            SampleTestCase(input_text="2 0 0 1", expected_output="-1"),
        ],
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Dijkstra",
        complexity_target=ComplexityBound(
            time_big_o="O((V+E) log V)", space_big_o="O(V+E)"
        ),
        pseudocode="dist[s]=0; pq; relax.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="print(5)", iteration=0)


def _state() -> V1State:
    return initial_state("r1", TargetAlgorithm.DIJKSTRA).model_copy(
        update={"spec": _spec(), "design": _design(), "attempt": _attempt()}
    )


class _ScriptedRunner:
    """RunSpec → 미리 정해진 RunResult queue."""

    def __init__(self, results: list[RunResult]) -> None:
        self._results = list(results)
        self.calls: list[RunSpec] = []

    def run(self, spec: RunSpec) -> RunResult:
        self.calls.append(spec)
        if not self._results:
            msg = "no more scripted results"
            raise RuntimeError(msg)
        return self._results.pop(0)


class _StubVerifier:
    """SymbolicVerifier impl — fixed violations + engaged count."""

    target_algorithm = TargetAlgorithm.DIJKSTRA

    def __init__(
        self,
        violations: list[InvariantViolation] | None = None,
        engaged: int = 3,
    ) -> None:
        self._violations = violations or []
        self._engaged = engaged

    def verify(
        self,
        spec: Any,
        design: Any,
        attempt: Any,
        sample_outputs: Any,
    ) -> list[InvariantViolation]:
        return list(self._violations)

    def count_engaged_samples(self, spec: Any) -> int:
        return self._engaged


def _ok(stdout: str, elapsed: int = 10) -> RunResult:
    return RunResult(
        status="OK", returncode=0, stdout=stdout, stderr="", elapsed_ms=elapsed
    )


def _rte(stderr: str = "Traceback") -> RunResult:
    return RunResult(
        status="RTE", returncode=1, stdout="", stderr=stderr, elapsed_ms=5
    )


def _tle() -> RunResult:
    return RunResult(
        status="TLE", returncode=-1, stdout="", stderr="", elapsed_ms=2000
    )


def _verifier_getter(verifier: _StubVerifier) -> Any:
    def get(_algo: TargetAlgorithm) -> _StubVerifier:
        return verifier

    return get


def test_executor_all_samples_pass_no_violations_overall_pass() -> None:
    runner = _ScriptedRunner([_ok("5"), _ok("3"), _ok("-1")])
    verifier = _StubVerifier(violations=[], engaged=3)
    node = make_executor_node(runner=runner, verifier_getter=_verifier_getter(verifier))
    new_state = node(_state())
    v = new_state.verification
    assert v is not None
    assert v.overall_pass is True
    assert v.failure_mode is FailureMode.NONE
    assert v.feedback is None
    assert v.samples_engaged == 3
    assert all(sr.passed for sr in v.sample_results)


def test_executor_sample_mismatch_no_violations_routes_to_architect() -> None:
    """Option B (§68): verifier invariants 통과 + sample mismatch =
    architect expected_output 오류 가설 → architect back-route."""
    runner = _ScriptedRunner([_ok("5"), _ok("999"), _ok("-1")])
    verifier = _StubVerifier(violations=[], engaged=3)
    node = make_executor_node(runner=runner, verifier_getter=_verifier_getter(verifier))
    new_state = node(_state())
    v = new_state.verification
    assert v is not None
    assert v.overall_pass is False
    assert v.failure_mode is FailureMode.SAMPLE_MISMATCH
    assert v.feedback is not None
    assert v.feedback.target_node is TargetNode.ARCHITECT
    assert v.feedback.blocking_signature == "sample-1-mismatch"
    assert "architect" in v.feedback.actionable_hint.lower()


def test_executor_sample_mismatch_with_violations_routes_to_coder() -> None:
    """invariant_violations 있으면 coder 의 실제 잘못 → coder 유지 (no back-route)."""
    runner = _ScriptedRunner([_ok("5"), _ok("999"), _ok("-1")])
    bogus_violation = InvariantViolation(
        invariant_kind="non_negative_distance",
        description="dist < 0",
        evidence={},
    )
    verifier = _StubVerifier(violations=[bogus_violation], engaged=3)
    node = make_executor_node(runner=runner, verifier_getter=_verifier_getter(verifier))
    new_state = node(_state())
    v = new_state.verification
    assert v is not None
    assert v.failure_mode is FailureMode.SAMPLE_MISMATCH
    assert v.feedback is not None
    assert v.feedback.target_node is TargetNode.CODER
    assert len(v.invariant_violations) == 1


def test_executor_sample_crash_routes_to_coder() -> None:
    runner = _ScriptedRunner([_ok("5"), _rte("NameError"), _ok("-1")])
    verifier = _StubVerifier(violations=[], engaged=3)
    node = make_executor_node(runner=runner, verifier_getter=_verifier_getter(verifier))
    new_state = node(_state())
    v = new_state.verification
    assert v is not None
    assert v.failure_mode is FailureMode.SAMPLE_CRASH
    assert v.feedback is not None
    assert v.feedback.blocking_signature == "sample-1-crash"


def test_executor_sample_timeout_classifies_correctly() -> None:
    runner = _ScriptedRunner([_ok("5"), _tle(), _ok("-1")])
    verifier = _StubVerifier(violations=[], engaged=3)
    node = make_executor_node(runner=runner, verifier_getter=_verifier_getter(verifier))
    new_state = node(_state())
    v = new_state.verification
    assert v is not None
    assert v.failure_mode is FailureMode.SAMPLE_TIMEOUT
    assert v.feedback is not None
    assert v.feedback.blocking_signature == "sample-1-timeout"


def test_executor_invariant_violation_when_samples_pass_but_verifier_rejects() -> None:
    runner = _ScriptedRunner([_ok("5"), _ok("3"), _ok("-1")])
    violation = InvariantViolation(
        invariant_kind="shortest_distance_optimal",
        description="sample 1: golden=3 but internal state diverged",
        evidence={"x": "y"},
    )
    verifier = _StubVerifier(violations=[violation], engaged=3)
    node = make_executor_node(runner=runner, verifier_getter=_verifier_getter(verifier))
    new_state = node(_state())
    v = new_state.verification
    assert v is not None
    assert v.failure_mode is FailureMode.INVARIANT_VIOLATION
    assert v.feedback is not None
    assert v.feedback.target_node is TargetNode.CODER
    assert v.feedback.blocking_signature == "shortest_distance_optimal-violated"
    assert len(v.invariant_violations) == 1


def test_executor_samples_engaged_propagated_from_verifier() -> None:
    runner = _ScriptedRunner([_ok("5"), _ok("3"), _ok("-1")])
    verifier = _StubVerifier(violations=[], engaged=1)
    node = make_executor_node(runner=runner, verifier_getter=_verifier_getter(verifier))
    new_state = node(_state())
    v = new_state.verification
    assert v is not None
    assert v.samples_engaged == 1


def test_executor_no_verifier_registered_engaged_zero() -> None:
    """verifier_getter 가 None 반환 시 samples_engaged=0 + verifier skip."""
    runner = _ScriptedRunner([_ok("5"), _ok("3"), _ok("-1")])

    def no_verifier(_algo: TargetAlgorithm) -> None:
        return None

    node = make_executor_node(runner=runner, verifier_getter=no_verifier)
    new_state = node(_state())
    v = new_state.verification
    assert v is not None
    assert v.samples_engaged == 0
    assert v.overall_pass is True


def test_executor_requires_spec_and_attempt() -> None:
    runner = _ScriptedRunner([])
    verifier = _StubVerifier()
    node = make_executor_node(runner=runner, verifier_getter=_verifier_getter(verifier))
    base = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    with pytest.raises(ValueError, match="state.spec and state.attempt"):
        node(base)
    only_spec = base.model_copy(update={"spec": _spec(), "design": _design()})
    with pytest.raises(ValueError, match="state.spec and state.attempt"):
        node(only_spec)


def test_executor_runs_sample_with_correct_stdin() -> None:
    runner = _ScriptedRunner([_ok("5"), _ok("3"), _ok("-1")])
    verifier = _StubVerifier(violations=[], engaged=3)
    node = make_executor_node(runner=runner, verifier_getter=_verifier_getter(verifier))
    node(_state())
    assert len(runner.calls) == 3
    assert runner.calls[0].stdin == "2 1 0 1\n0 1 5"
    assert runner.calls[1].stdin == "3 2 0 2\n0 1 1\n1 2 2"
    assert runner.calls[2].stdin == "2 0 0 1"
    for call in runner.calls:
        assert call.cmd == ["python3", "solution.py"]
