"""v2 QA 스테이지 통합테스트 — with_qa=True (Phase 3 M5 step3).

suite_assembler 후 QA 리뷰어 4종 병렬 fan-out → aggregator(N11) → 게이트 배선을
mock LLM + scripted runner 로 검증:
1. 전원 통과: qa_report.overall_pass → end_success, qa_reviews 4종(dedup).
2. 일부 실패: failed_kinds 기록 + final_status='fail_qa' (단발 게이트 — back-route
   루프는 후속 step).
3. build guard: with_qa=True 는 with_test_suite=True 필수.
+ route_after_qa 단위: report 부재/실패 → end_qa, 통과 → end_success.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

import pytest

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import (
    AlgorithmDesign,
    BlueprintFormalization,
    ComplexityBound,
    ConstraintRange,
    EdgeCaseSpec,
    GeneratorContract,
    Invariant,
    IOContract,
    IOFieldSpec,
    IOSchema,
    NarrativeDraft,
    NarrativeFaithfulnessReport,
    ProblemSpec,
    QAReport,
    QAReview,
    QAReviewerKind,
    SampleTestCase,
    ScaleFamily,
    SolutionAttempt,
    StrategySeed,
    TargetAlgorithm,
)
from ipe.v2.graph import build_v2_graph
from ipe.v2.router import route_after_qa
from ipe.v2.state import V2State, initial_v2_state

ALL_KINDS: tuple[QAReviewerKind, ...] = get_args(QAReviewerKind)
_SAMPLE_INPUTS = ["i0", "i1", "i2"]


# ---------- modeling/synthesis mocks (suite 통합테스트와 동일 골격) ----------


class _FixedStrategistLLM:
    def seed(self, state: Any) -> StrategySeed:
        return StrategySeed(reduction_core=TargetAlgorithm.SORT, domain="logistics")


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


class _SpecBridgeLLM:
    def author(self, state: Any) -> ProblemSpec:
        return ProblemSpec(
            target_algorithm=TargetAlgorithm.SORT,
            title="t",
            description="placeholder",
            io_contract=IOContract(input_format="i", output_format="o"),
            sample_testcases=[
                SampleTestCase(input_text=i, expected_output=f"ans-{i}")
                for i in _SAMPLE_INPUTS
            ],
        )


class _DesignerLLM:
    def generate(self, state: Any) -> AlgorithmDesign:
        return AlgorithmDesign(
            algorithm_name="sort",
            complexity_target=ComplexityBound(
                time_big_o="O(N log N)", space_big_o="O(N)"
            ),
            pseudocode="sort.",
            invariants=[Invariant(kind="sorted", description="x")],
        )


class _CoderLLM:
    def __init__(self, code: str) -> None:
        self._code = code

    def generate(self, state: Any) -> SolutionAttempt:
        return SolutionAttempt(code=self._code, iteration=0)


class _FixedGeneratorDesignerLLM:
    def design(self, state: Any) -> GeneratorContract:
        return GeneratorContract(
            scale_families=(
                ScaleFamily(
                    name="small",
                    case_count=2,
                    field_bounds=(
                        ConstraintRange(name="N", min_value=5, max_value=5),
                    ),
                ),
            ),
            edge_cases=(EdgeCaseSpec(name="zero"),),
            determinism_seed=7,
        )


class _EchoRunner:
    def run(self, spec: RunSpec) -> RunResult:
        _ = sorted(Path(spec.cwd).glob("*.py"))
        return RunResult(
            status="OK",
            returncode=0,
            stdout=f"ans-{spec.stdin}",
            stderr="",
            elapsed_ms=1,
        )


class _QAReviewerLLM:
    """kind 별 pass/fail 스크립트 — 병렬 4종 mock."""

    def __init__(self, passed: bool, kind: QAReviewerKind) -> None:
        self._passed = passed
        self._kind = kind

    def review(self, state: Any, *, kind: QAReviewerKind) -> QAReview:
        return QAReview(kind=self._kind, passed=self._passed, rationale="scripted")


def _final(raw: Any) -> V2State:
    return raw if isinstance(raw, V2State) else V2State.model_validate(raw)


def _qa_graph(*, fail_kinds: tuple[QAReviewerKind, ...] = ()) -> Any:
    qa_llms: dict[QAReviewerKind, Any] = {
        kind: _QAReviewerLLM(kind not in fail_kinds, kind) for kind in ALL_KINDS
    }
    return build_v2_graph(
        strategist_llm=_FixedStrategistLLM(),
        formalizer_llm=_FixedFormalizerLLM(),
        narrative_llm=_FixedNarrativeLLM(),
        faithfulness_llm=_FaithfulLLM(),
        with_synthesis=True,
        spec_bridge_llm=_SpecBridgeLLM(),
        designer_llm=_DesignerLLM(),
        golden_llms=[_CoderLLM("# G0"), _CoderLLM("# G1")],
        brute_llm=_CoderLLM("# B"),
        golden_origins=["opus", "sonnet"],
        runner=_EchoRunner(),
        verifier_getter=lambda _a: None,
        with_test_suite=True,
        generator_designer_llm=_FixedGeneratorDesignerLLM(),
        with_qa=True,
        qa_reviewer_llms=qa_llms,
    )


def _run(graph: Any, run_id: str) -> V2State:
    return _final(
        graph.invoke(
            initial_v2_state(run_id, TargetAlgorithm.SORT),
            config={"recursion_limit": 60},
        )
    )


# ---------- 1. QA 전원 통과 → 출하 ----------


def test_qa_pipeline_all_pass() -> None:
    final = _run(_qa_graph(), "run-qa-ok")

    assert final.final_status == "success"
    assert final.test_suite is not None and final.test_suite.is_assembled
    assert len(final.qa_reviews) == 4  # 4 병렬 리뷰어, dedup 멱등
    assert {r.kind for r in final.qa_reviews} == set(ALL_KINDS)
    assert final.qa_report is not None
    assert final.qa_report.overall_pass is True


# ---------- 2. 일부 실패 → fail_qa 게이트 ----------


def test_qa_pipeline_blocks_on_failure() -> None:
    final = _run(_qa_graph(fail_kinds=("leakage",)), "run-qa-fail")

    assert final.final_status == "fail_qa"
    assert final.qa_report is not None
    assert final.qa_report.overall_pass is False
    assert final.qa_report.failed_kinds == ("leakage",)
    # suite 까지는 정상 생산 — QA 게이트가 출하만 막음
    assert final.test_suite is not None and final.test_suite.is_assembled


# ---------- 3. build guard ----------


def test_with_qa_requires_test_suite() -> None:
    with pytest.raises(ValueError, match="with_qa"):
        build_v2_graph(with_qa=True, with_synthesis=True)


# ---------- route_after_qa 단위 ----------


def test_route_after_qa_decisions() -> None:
    base = initial_v2_state("r", TargetAlgorithm.SORT)
    assert route_after_qa(base) == "end_qa"  # report 부재 = 미통과
    ok = base.model_copy(
        update={
            "qa_report": QAReport(reviews=(QAReview(kind="ambiguity", passed=True),))
        }
    )
    assert route_after_qa(ok) == "end_success"
    bad = base.model_copy(
        update={
            "qa_report": QAReport(reviews=(QAReview(kind="leakage", passed=False),))
        }
    )
    assert route_after_qa(bad) == "end_qa"
