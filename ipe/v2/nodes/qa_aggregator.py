"""qa_aggregator 노드 — QA 리뷰 fan-in 집계 (M5 step3, RFC N11). LLM 없음.

4 병렬 리뷰어(N10a-d)가 ``qa_reviews`` reducer 채널에 쌓은 리뷰를 deterministic
하게 ``QAReport`` 로 집계한다. 출하 게이트 판단(라우팅)은 router 의
``route_after_qa`` — 이 노드는 집계만 (판단/집계 분리, v1 aggregator 패턴).

fan-in join 노드지만 **partial dict** 반환 — full-state 재emit 으로 reducer 채널을
건드리지 않는 M0/M2 규율 유지.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ipe.v1.schema import QAReport

from ..state import V2State


def make_qa_aggregator_node() -> Callable[[V2State], dict[str, Any]]:
    """factory — ``state.qa_reviews`` → ``QAReport`` (``state.qa_report``)."""

    def node(state: V2State) -> dict[str, Any]:
        if not state.qa_reviews:
            msg = "qa_aggregator requires non-empty state.qa_reviews"
            raise ValueError(msg)
        report = QAReport(reviews=tuple(state.qa_reviews))
        return {"qa_report": report}

    return node
