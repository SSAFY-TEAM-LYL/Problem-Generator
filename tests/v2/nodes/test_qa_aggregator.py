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
