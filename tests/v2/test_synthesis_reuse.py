"""M2 synthesis 노드의 V2State 재사용 검증 (Phase 3 v2 synthesis 통합 step2a).

v1 의 designer/synthesis_coder/reconciler/synth_bridge/executor 노드(V1State 타입)가
V2State 에서도 **duck-typing 으로 동작**함을 노드별로 실증 — step2b 그래프 배선의
선결 검증. V2State 적응 3요소를 증명:
1. ``target_algorithm`` property (=spec.target_algorithm / seed fallback).
2. ``design``/``attempt`` 채널 (executor/synth_bridge 출력 수용).

scripted runner 로 sandbox 없이 결정론 검증 (cast(Any) = 프로덕션 graph 의 재사용 방식).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.nodes import (
    make_designer_node,
    make_executor_node,
    make_reconciler_node,
    make_synth_bridge_node,
    make_synthesis_coder_node,
)
from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    Invariant,
    IOContract,
    ProblemSpec,
    ReconciliationResult,
    SampleTestCase,
    SolutionAttempt,
    SolutionCandidate,
    TargetAlgorithm,
)
from ipe.v2.state import V2State, initial_v2_state


def _spec(algo: TargetAlgorithm = TargetAlgorithm.TWO_SUM) -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=algo,
        title="t",
        description="d",
        io_contract=IOContract(input_format="i", output_format="o"),
        sample_testcases=[
            SampleTestCase(input_text=f"i{n}", expected_output=f"ans-i{n}")
            for n in range(3)
        ],
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="two_sum",
        complexity_target=ComplexityBound(time_big_o="O(n)", space_big_o="O(n)"),
        pseudocode="hash map.",
        invariants=[Invariant(kind="unique_pair", description="x")],
    )


def _state_with_spec(*, design: bool = False) -> V2State:
    base = initial_v2_state("run-reuse", TargetAlgorithm.DIJKSTRA)
    update: dict[str, Any] = {"spec": _spec()}
    if design:
        update["design"] = _design()
    return base.model_copy(update=update)


class _FixedDesignerLLM:
    def generate(self, state: Any) -> AlgorithmDesign:
        return _design()


class _FixedCoderLLM:
    def __init__(self, code: str) -> None:
        self._code = code

    def generate(self, state: Any) -> SolutionAttempt:
        return SolutionAttempt(code=self._code, iteration=0)


class _MarkerRunner:
    """cwd 의 .py(sol.py/solution.py 무관)를 읽어 marker 로 출력 결정."""

    def __init__(self, fn: Callable[[str, str], tuple[str, str]]) -> None:
        self._fn = fn

    def run(self, spec: RunSpec) -> RunResult:
        py = sorted(Path(spec.cwd).glob("*.py"))
        code = py[0].read_text(encoding="utf-8") if py else ""
        status, stdout = self._fn(code, spec.stdin)
        return RunResult(
            status=status,  # type: ignore[arg-type]
            returncode=0 if status == "OK" else 1,
            stdout=stdout,
            stderr="" if status == "OK" else "boom",
            elapsed_ms=1,
        )


def _ok(_code: str, stdin: str) -> tuple[str, str]:
    return ("OK", f"ans-{stdin}")


# ---------- target_algorithm property ----------


def test_target_algorithm_property_uses_spec() -> None:
    state = _state_with_spec()  # spec.target_algorithm = TWO_SUM
    assert state.target_algorithm is TargetAlgorithm.TWO_SUM  # seed=DIJKSTRA 아님


def test_target_algorithm_property_falls_back_to_seed() -> None:
    state = initial_v2_state("r", TargetAlgorithm.BFS)  # spec 없음
    assert state.target_algorithm is TargetAlgorithm.BFS


# ---------- M2 노드 V2State 재사용 ----------


def test_designer_node_reuse_populates_design() -> None:
    node = cast(Any, make_designer_node(_FixedDesignerLLM()))
    out = node(_state_with_spec())
    assert isinstance(out, V2State)
    assert out.design is not None
    assert out.design.algorithm_name == "two_sum"


def test_synthesis_coder_node_reuse_emits_candidate() -> None:
    node = cast(
        Any,
        make_synthesis_coder_node(
            _FixedCoderLLM("# G"), role="golden", origin="opus", fanout_index=0
        ),
    )
    out = node(_state_with_spec(design=True))
    assert out["candidates"][0].origin == "opus"
    assert out["candidates"][0].code == "# G"


def test_reconciler_node_reuse_records_reconciliation() -> None:
    state = _state_with_spec().model_copy(
        update={
            "candidates": [
                SolutionCandidate(role="golden", origin="opus", code="# G"),
                SolutionCandidate(role="brute", origin="naive", code="# B"),
            ]
        }
    )
    node = cast(Any, make_reconciler_node(_MarkerRunner(_ok)))
    out = node(state)
    r = out["reconciliation"]
    assert isinstance(r, ReconciliationResult)
    assert r.all_agree is True
    assert r.canonical_code == "# G"


def test_synth_bridge_node_reuse_emits_attempt() -> None:
    state = _state_with_spec().model_copy(
        update={
            "reconciliation": ReconciliationResult(
                all_agree=True,
                canonical_code="# CANON",
                adopted_origin="opus",
                candidate_count=2,
            )
        }
    )
    node = cast(Any, make_synth_bridge_node())
    out = node(state)
    assert out["attempt"].code == "# CANON"


def test_executor_node_reuse_populates_verification() -> None:
    state = _state_with_spec(design=True).model_copy(
        update={"attempt": SolutionAttempt(code="# sol", iteration=0)}
    )
    node = cast(
        Any,
        make_executor_node(runner=_MarkerRunner(_ok), verifier_getter=lambda _a: None),
    )
    out = node(state)
    assert isinstance(out, V2State)
    assert out.verification is not None
    # spec.sample expected = 'ans-i{n}', runner 도 'ans-i{n}' → 전부 pass
    assert out.verification.overall_pass is True
