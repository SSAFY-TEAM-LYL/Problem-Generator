"""v2 full 파이프라인 통합테스트 — with_synthesis=True (Phase 3 통합 step2b).

modeling(strategist→formalizer→narrative→faithfulness) → spec_bridge → designer →
golden/brute fan-out → reconcile → synth_bridge → executor 까지 mock LLM + scripted
runner 로 end-to-end 검증:
1. success: faithful + golden×2/brute 합의 + executor pass → end_success, 전 아티팩트 populate.
2. synthesis rejected: golden 불일치 → end_synthesis_rejected.
3. verification fail: 합의했으나 canonical 이 sample mismatch → end_verification.
4. build guard: with_synthesis=True + golden_llms 누락 → 거부.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import (
    AlgorithmDesign,
    BlueprintFormalization,
    ComplexityBound,
    Invariant,
    IOContract,
    IOFieldSpec,
    IOSchema,
    NarrativeDraft,
    NarrativeFaithfulnessReport,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    StrategySeed,
    TargetAlgorithm,
)
from ipe.v2.graph import build_v2_graph
from ipe.v2.state import V2State, initial_v2_state

_INPUTS = ["i0", "i1", "i2"]


# ---------- modeling mocks ----------


class _FixedStrategistLLM:
    def seed(self, state: Any) -> StrategySeed:
        return StrategySeed(reduction_core=TargetAlgorithm.DIJKSTRA, domain="logistics")


class _FixedFormalizerLLM:
    def formalize(self, state: Any) -> BlueprintFormalization:
        return BlueprintFormalization(
            io_schema=IOSchema(
                inputs=(IOFieldSpec(name="N", type="int"),),
                output_type="int",
                output_format="단일 정수",
            )
        )


class _FixedNarrativeLLM:
    def render(self, state: Any, *, hidden: bool) -> NarrativeDraft:
        return NarrativeDraft(scenario="물류 시나리오")


class _FaithfulLLM:
    def assess(self, state: Any) -> NarrativeFaithfulnessReport:
        return NarrativeFaithfulnessReport(faithful=True)


# ---------- synthesis mocks ----------


class _SpecBridgeLLM:
    """expected = f'{prefix}-{input}' 인 spec 저작. prefix='ans' 면 runner 와 일치."""

    def __init__(self, prefix: str = "ans") -> None:
        self._prefix = prefix

    def author(self, state: Any) -> ProblemSpec:
        return ProblemSpec(
            target_algorithm=TargetAlgorithm.DIJKSTRA,
            title="t",
            description="placeholder",
            io_contract=IOContract(input_format="i", output_format="o"),
            sample_testcases=[
                SampleTestCase(input_text=i, expected_output=f"{self._prefix}-{i}")
                for i in _INPUTS
            ],
        )


class _DesignerLLM:
    def generate(self, state: Any) -> AlgorithmDesign:
        return AlgorithmDesign(
            algorithm_name="dijkstra",
            complexity_target=ComplexityBound(
                time_big_o="O(E log V)", space_big_o="O(V)"
            ),
            pseudocode="relax edges.",
            invariants=[Invariant(kind="non_negative", description="x")],
        )


class _CoderLLM:
    def __init__(self, code: str) -> None:
        self._code = code

    def generate(self, state: Any) -> SolutionAttempt:
        return SolutionAttempt(code=self._code, iteration=0)


class _MarkerRunner:
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


def _by_marker(code: str, stdin: str) -> tuple[str, str]:
    if "CRASH" in code:
        return ("RTE", "")
    if "WRONG" in code:
        return ("OK", f"wrong-{stdin}")
    return ("OK", f"ans-{stdin}")


def _final(raw: Any) -> V2State:
    return raw if isinstance(raw, V2State) else V2State.model_validate(raw)


def _full_graph(
    *, spec_prefix: str = "ans", golden_codes: list[str], brute_code: str = "# B"
) -> Any:
    return build_v2_graph(
        strategist_llm=_FixedStrategistLLM(),
        formalizer_llm=_FixedFormalizerLLM(),
        narrative_llm=_FixedNarrativeLLM(),
        faithfulness_llm=_FaithfulLLM(),
        with_synthesis=True,
        spec_bridge_llm=_SpecBridgeLLM(spec_prefix),
        designer_llm=_DesignerLLM(),
        golden_llms=[_CoderLLM(c) for c in golden_codes],
        brute_llm=_CoderLLM(brute_code),
        golden_origins=["opus", "sonnet"],
        runner=_MarkerRunner(_by_marker),
        verifier_getter=lambda _a: None,
    )


def _run(graph: Any, run_id: str) -> V2State:
    return _final(
        graph.invoke(
            initial_v2_state(run_id, TargetAlgorithm.DIJKSTRA),
            config={"recursion_limit": 50},
        )
    )


# ---------- 1. success ----------


def test_full_pipeline_success() -> None:
    graph = _full_graph(golden_codes=["# G0", "# G1"])
    final = _run(graph, "run-full-ok")

    assert final.final_status == "success"
    # modeling 아티팩트
    assert final.strategy is not None
    assert final.narrative is not None
    assert final.faithfulness is not None and final.faithfulness.faithful is True
    # synthesis 아티팩트
    assert final.spec is not None
    assert final.spec.target_algorithm is TargetAlgorithm.DIJKSTRA  # blueprint carry-over
    assert final.design is not None
    assert len(final.candidates) == 3  # golden×2 + brute, dedup reducer
    assert final.reconciliation is not None and final.reconciliation.all_agree is True
    assert final.attempt is not None and final.attempt.code == "# G0"  # canonical
    assert final.verification is not None and final.verification.overall_pass is True


# ---------- 2. synthesis rejected ----------


def test_full_pipeline_synthesis_rejected() -> None:
    graph = _full_graph(golden_codes=["# G0", "# WRONG G1"])
    final = _run(graph, "run-rej")

    assert final.final_status == "fail_synthesis_rejected"
    assert final.reconciliation is not None and final.reconciliation.all_agree is False
    assert final.attempt is None  # synth_bridge 미실행


# ---------- 3. verification fail ----------


def test_full_pipeline_verification_fail() -> None:
    # spec expected = 'zzz-*' 이지만 runner 는 'ans-*' → 합의는 하되 sample mismatch
    graph = _full_graph(spec_prefix="zzz", golden_codes=["# G0", "# G1"])
    final = _run(graph, "run-vfail")

    assert final.final_status == "fail_verification"
    assert final.reconciliation is not None and final.reconciliation.all_agree is True
    assert final.attempt is not None  # bridge 됨
    assert final.verification is not None and final.verification.overall_pass is False


# ---------- 4. build guard ----------


def test_with_synthesis_requires_golden_and_brute() -> None:
    with pytest.raises(ValueError, match="golden_llms"):
        build_v2_graph(with_synthesis=True, brute_llm=_CoderLLM("# B"))
