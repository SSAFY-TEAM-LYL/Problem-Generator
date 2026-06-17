"""하이브리드(v1 생성 + v2 검증) 파이프라인 — QA 게이트 로직 테스트.

LLM/그래프는 mock — _qa_state(body→V2State 재구성) + qa_gate(4-charter pass/fail)
의 순수 로직을 결정론 검증. 실 LLM(v1 full 생성 + 실 QA)은 CLI 실행으로 입증.
"""

from __future__ import annotations

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import (
    GeneratedTestCase,
    IOContract,
    ProblemSpec,
    QAFinding,
    QAReview,
    QAReviewerKind,
    SampleTestCase,
    SolutionAttempt,
    TargetAlgorithm,
)
from ipe.v1.state import V1State, initial_state
from ipe.v2.canonical_ingest import canonical_body
from ipe.v2.hybrid_ingest import (
    _EASY_CHARTERS,
    _build_reviewers,
    _hybrid_body,
    _qa_state,
    qa_gate,
)
from ipe.v2.nodes.qa_reviewer import QAReviewerLLM
from ipe.v2.state import V2State


def _success_state() -> V1State:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="두 거래 합",
        description="합이 target 인 서로 다른 두 수의 쌍 개수를 센다.",
        io_contract=IOContract(input_format="N\\na..\\nT", output_format="개수"),
        sample_testcases=[
            SampleTestCase(input_text="3\\n1 2 3\\n5", expected_output="1"),
            SampleTestCase(input_text="2\\n1 1\\n2", expected_output="1"),
            SampleTestCase(input_text="1\\n5\\n5", expected_output="0"),
        ],
    )
    return initial_state("r1", TargetAlgorithm.TWO_SUM).model_copy(
        update={
            "spec": spec,
            "attempt": SolutionAttempt(code="print(0)", iteration=0),
            "final_status": "success",
        }
    )


class _MockReviewer:
    """QAReviewerLLM 구조적 mock — passed 고정."""

    def __init__(self, passed: bool) -> None:
        self._passed = passed

    def review(self, state: V2State, *, kind: QAReviewerKind) -> QAReview:
        findings = (
            ()
            if self._passed
            else (QAFinding(severity="blocker", description="비유일 정답"),)
        )
        return QAReview(kind=kind, passed=self._passed, findings=findings)


def _reviewers(
    *, fail: QAReviewerKind | None = None
) -> dict[QAReviewerKind, QAReviewerLLM]:
    out: dict[QAReviewerKind, QAReviewerLLM] = {
        k: _MockReviewer(True) for k in _EASY_CHARTERS
    }
    if fail is not None:
        out[fail] = _MockReviewer(False)
    return out


def test_default_reviewers_scope_to_easy_charters() -> None:
    """하이브리드 기본 QA = ambiguity+fairness (leakage/difficulty 제외 — 실측 근거)."""
    rv = _build_reviewers()
    assert set(rv) == {"ambiguity", "fairness"}
    assert "leakage" not in rv  # 고전 easy 문제를 본질적으로 reject = B2B 잡음
    assert "difficulty" not in rv  # 빈약 TC 지적 — 풀 채점셋 전까지 보류


def test_qa_state_builds_reviewable_v2state() -> None:
    body = canonical_body(_success_state(), run_id="h1", seed="two_sum")
    state = _qa_state(body, "h1")
    assert state.spec is not None
    assert state.spec.title == "두 거래 합"
    assert state.narrative is not None
    assert state.test_suite is not None
    assert len(state.test_suite.cases) == 3  # samples → test_suite cases


def test_qa_gate_pass_when_all_reviewers_pass() -> None:
    state = _qa_state(
        canonical_body(_success_state(), run_id="h1", seed="two_sum"), "h1"
    )
    assert qa_gate(state, _reviewers()).overall_pass is True


def test_qa_gate_fail_on_ambiguity() -> None:
    """two_sum 비유일 같은 모호성을 ambiguity charter 가 잡으면 출하 차단."""
    state = _qa_state(
        canonical_body(_success_state(), run_id="h1", seed="two_sum"), "h1"
    )
    report = qa_gate(state, _reviewers(fail="ambiguity"))
    assert report.overall_pass is False
    assert "ambiguity" in [r.kind for r in report.reviews if not r.passed]


class _StubInputGen:
    """다양 입력 생성 mock — 고정 케이스 emit."""

    def __init__(self, cases: tuple[GeneratedTestCase, ...]) -> None:
        self._cases = cases

    def generate(
        self, spec: ProblemSpec, *, target_count: int
    ) -> tuple[GeneratedTestCase, ...]:
        return self._cases


class _OkRunner:
    """golden mock — 모든 입력 OK (expected 채워짐)."""

    def run(self, spec: RunSpec) -> RunResult:
        return RunResult(
            status="OK", returncode=0, stdout="r\n", stderr="", elapsed_ms=3
        )


def test_hybrid_body_expands_grading_suite() -> None:
    """_hybrid_body: v1 full success → 풀 채점셋 확장 → body 채점셋이 sample 초과."""
    gen = _StubInputGen(
        (
            GeneratedTestCase(input_text="9\n1 2 3 4 5 6 7 8 9\n10", category="large"),
            GeneratedTestCase(input_text="1\n0\n0", category="edge_single"),
        )
    )
    body = _hybrid_body(
        _success_state(), "h-exp", "two_sum", generator=gen, runner=_OkRunner()
    )
    cases = body["package"]["test_suite"]["cases"]
    assert len(cases) == 5  # 3 samples + 2 generated (sample 3 보다 큼)
    assert {c["category"] for c in cases} >= {"sample", "large", "edge_single"}
    assert body["package"]["test_suite"]["origin"] == "golden"  # reconciliation 없음


def test_hybrid_body_falls_back_to_samples_on_expansion_failure() -> None:
    """확장 실패(생성기 예외) → samples 폴백 — 검증된 문제를 잃지 않고 적재 가능."""

    class _BoomGen:
        def generate(
            self, spec: ProblemSpec, *, target_count: int
        ) -> tuple[GeneratedTestCase, ...]:
            msg = "LLM down"
            raise RuntimeError(msg)

    body = _hybrid_body(
        _success_state(), "h-fb", "two_sum", generator=_BoomGen(), runner=_OkRunner()
    )
    suite = body["package"]["test_suite"]
    assert suite["origin"] == "canonical_samples"  # 폴백 (확장 안 됨)
    assert {c["category"] for c in suite["cases"]} == {"sample"}


def test_hybrid_expanded_suite_flows_into_qa_state() -> None:
    """확장 채점셋이 _qa_state 로 흘러 QA 가 풀셋을 검수한다 (sample 만이 아님)."""
    gen = _StubInputGen(
        (GeneratedTestCase(input_text="4\n1 2 3 4\n5", category="medium"),)
    )
    body = _hybrid_body(
        _success_state(), "h-qa", "two_sum", generator=gen, runner=_OkRunner()
    )
    state = _qa_state(body, "h-qa")
    assert state.test_suite is not None
    assert len(state.test_suite.cases) == 4  # 3 samples + 1 generated
