"""QA aggregator 노드 단위 테스트 (Phase 3 M5 step3, RFC N11).

deterministic fan-in: state.qa_reviews → QAReport (partial dict). LLM 없음.
"""

from __future__ import annotations

import pytest

from ipe.v1.schema import QAReview, TargetAlgorithm
from ipe.v2.nodes import make_qa_aggregator_node
from ipe.v2.state import initial_v2_state


def test_aggregator_builds_report_from_reviews() -> None:
    state = initial_v2_state("r", TargetAlgorithm.SORT).model_copy(
        update={
            "qa_reviews": [
                QAReview(kind="ambiguity", passed=True),
                QAReview(kind="leakage", passed=False),
            ]
        }
    )
    out = make_qa_aggregator_node()(state)
    assert isinstance(out, dict)
    report = out["qa_report"]
    assert report.overall_pass is False
    assert report.failed_kinds == ("leakage",)


def test_aggregator_all_pass() -> None:
    state = initial_v2_state("r", TargetAlgorithm.SORT).model_copy(
        update={"qa_reviews": [QAReview(kind="fairness", passed=True)]}
    )
    out = make_qa_aggregator_node()(state)
    assert out["qa_report"].overall_pass is True


def test_aggregator_requires_reviews() -> None:
    bare = initial_v2_state("r", TargetAlgorithm.SORT)
    with pytest.raises(ValueError, match="qa_reviews"):
        make_qa_aggregator_node()(bare)


def test_aggregator_keeps_latest_per_kind() -> None:
    """back-route(B) 재리뷰 시 reducer 에 라운드가 누적 — kind 별 **최신** 리뷰만
    집계해야 수정 반영 후 통과가 가능 (옛 fail 리뷰가 영구 블록하지 않게)."""
    state = initial_v2_state("r", TargetAlgorithm.SORT).model_copy(
        update={
            "qa_reviews": [
                QAReview(kind="ambiguity", passed=False, rationale="round1"),
                QAReview(kind="fairness", passed=True),
                QAReview(kind="ambiguity", passed=True, rationale="round2"),
            ]
        }
    )
    report = make_qa_aggregator_node()(state)["qa_report"]
    assert len(report.reviews) == 2  # kind 별 1개
    assert report.overall_pass is True  # ambiguity 는 round2(최신) 판정
    by_kind = {r.kind: r for r in report.reviews}
    assert by_kind["ambiguity"].rationale == "round2"
