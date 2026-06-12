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
    """factory — ``state.qa_reviews`` → ``QAReport`` (``state.qa_report``).

    back-route(B) 재리뷰 시 reducer 채널에 라운드가 누적되므로 **kind 별 최신
    리뷰만** 집계한다 (reducer concat 순서 = append 순 → last write wins). 옛 fail
    리뷰가 남아 있으면 수정 반영 후에도 영구 블록되기 때문. 단발 경로(라운드 1회)
    에선 기존 동작과 동일.
    """

    def node(state: V2State) -> dict[str, Any]:
        if not state.qa_reviews:
            msg = "qa_aggregator requires non-empty state.qa_reviews"
            raise ValueError(msg)
        latest = {r.kind: r for r in state.qa_reviews}
        report = QAReport(reviews=tuple(latest.values()))
        return {"qa_report": report}

    return node
