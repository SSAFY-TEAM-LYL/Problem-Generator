"""병렬 Solution Synthesis 서브그래프 통합테스트 (Phase 3 M2 step3).

mock CoderLLM(고정 code) + scripted runner 로 langgraph fan-out/fan-in 검증:
1. golden×K + brute 가 ``candidates`` reducer 채널에 전부 누적 (순서 무관, 중복 없음).
2. reconciler fan-in **1회** — 전부 일치 시 canonical 채택 (golden_0 reference).
3. golden 불일치 시 ``all_agree=False`` (reject 신호).
4. golden 1 + brute 교차검증 성립.
5. golden 0개 → build 거부.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    Invariant,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    TargetAlgorithm,
)
from ipe.v1.state import V1State, initial_state
from ipe.v1.synthesis_graph import build_synthesis_graph


def _spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="t",
        description="d",
        io_contract=IOContract(input_format="i", output_format="o"),
        sample_testcases=[
            SampleTestCase(input_text="i1", expected_output="o1"),
            SampleTestCase(input_text="i2", expected_output="o2"),
            SampleTestCase(input_text="i3", expected_output="o3"),
        ],
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="two_sum",
        complexity_target=ComplexityBound(time_big_o="O(n)", space_big_o="O(n)"),
        pseudocode="hash map.",
        invariants=[Invariant(kind="unique_pair", description="x")],
    )


def _state_with_spec() -> V1State:
    base = initial_state("run-synth", TargetAlgorithm.TWO_SUM)
    return base.model_copy(update={"spec": _spec(), "design": _design()})


class _FixedCoderLLM:
    def __init__(self, code: str) -> None:
        self._code = code

    def generate(self, state: V1State) -> SolutionAttempt:
        return SolutionAttempt(code=self._code, iteration=0)


class _ScriptedRunner:
    def __init__(self, fn: Callable[[str, str], tuple[str, str]]) -> None:
        self._fn = fn

    def run(self, spec: RunSpec) -> RunResult:
        code = (Path(spec.cwd) / "sol.py").read_text(encoding="utf-8")
        status, stdout = self._fn(code, spec.stdin)
        return RunResult(
            status=status,  # type: ignore[arg-type]
            returncode=0 if status == "OK" else 1,
            stdout=stdout,
            stderr="" if status == "OK" else "boom",
            elapsed_ms=1,
        )


def _by_marker(code: str, stdin: str) -> tuple[str, str]:
    """code 에 WRONG 있으면 다른 답, 아니면 동일 답 (출력은 stdin 으로만 결정)."""
    if "CRASH" in code:
        return ("RTE", "")
    if "WRONG" in code:
        return ("OK", f"wrong-{stdin}")
    return ("OK", f"ans-{stdin}")


def _final(raw: Any) -> V1State:
    if isinstance(raw, V1State):
        return raw
    return V1State.model_validate(raw)


def _two_golden_graph(runner: _ScriptedRunner, *, g1_code: str = "# G1") -> Any:
    return build_synthesis_graph(
        golden_llms=[_FixedCoderLLM("# G0"), _FixedCoderLLM(g1_code)],
        brute_llm=_FixedCoderLLM("# B"),
        runner=runner,
        golden_origins=["opus", "sonnet"],
    )


def test_fanout_accumulates_all_candidates_without_dup() -> None:
    graph = _two_golden_graph(_ScriptedRunner(_by_marker))
    final = _final(graph.invoke(_state_with_spec()))

    assert len(final.candidates) == 3  # 2 golden + 1 brute, reducer 중복 없음
    labels = sorted((c.role, c.origin) for c in final.candidates)
    assert labels == [("brute", "naive"), ("golden", "opus"), ("golden", "sonnet")]


def test_reconciler_adopts_golden0_when_all_agree() -> None:
    graph = _two_golden_graph(_ScriptedRunner(_by_marker))
    final = _final(graph.invoke(_state_with_spec()))

    r = final.reconciliation
    assert r is not None
    assert r.all_agree is True
    assert r.adopted_origin == "opus"  # fanout_index 0 = reference
    assert r.canonical_code == "# G0"
    assert r.candidate_count == 3  # fan-in 이 모든 후보 본 뒤 1회 실행


def test_golden_disagreement_rejected() -> None:
    graph = _two_golden_graph(_ScriptedRunner(_by_marker), g1_code="# WRONG G1")
    final = _final(graph.invoke(_state_with_spec()))

    r = final.reconciliation
    assert r is not None
    assert r.all_agree is False
    assert r.canonical_code is None
    assert any("sonnet" in d for d in r.disagreements)


def test_single_golden_plus_brute_agrees() -> None:
    graph = build_synthesis_graph(
        golden_llms=[_FixedCoderLLM("# G0")],
        brute_llm=_FixedCoderLLM("# B"),
        runner=_ScriptedRunner(_by_marker),
    )
    final = _final(graph.invoke(_state_with_spec()))

    assert len(final.candidates) == 2
    assert final.reconciliation is not None
    assert final.reconciliation.all_agree is True


def test_empty_golden_llms_raises() -> None:
    with pytest.raises(ValueError, match="golden"):
        build_synthesis_graph(
            golden_llms=[],
            brute_llm=_FixedCoderLLM("# B"),
            runner=_ScriptedRunner(_by_marker),
        )


def test_origins_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="golden_origins"):
        build_synthesis_graph(
            golden_llms=[_FixedCoderLLM("# G0"), _FixedCoderLLM("# G1")],
            brute_llm=_FixedCoderLLM("# B"),
            runner=_ScriptedRunner(_by_marker),
            golden_origins=["only-one"],
        )
