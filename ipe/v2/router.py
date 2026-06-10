"""v2 modeling-layer 라우터 (Phase 3 M3 step5).

faithfulness round-trip 후 결정론적 분기: 충실하면 success, 왜곡이면 narrative
재생성(싼 반복), budget 소진 시 fail_faithfulness. v1 router 의 enum/threshold
결정론 패턴(D안 H1)과 동일 — prose 판단 없이 typed report + iteration cap 으로만.
"""

from __future__ import annotations

from typing import Literal

from .state import V2State

FaithfulnessDecision = Literal["end_success", "regen", "end_faithfulness"]


def route_after_faithfulness(state: V2State) -> FaithfulnessDecision:
    """faithfulness 후 다음 step 결정.

    1. ``faithfulness.faithful=True`` → ``end_success`` (출하).
    2. 왜곡(faithful=False)이고 ``iteration < max_iterations`` → ``regen``
       (iteration++ 후 narrative 재생성, 싼 반복).
    3. 왜곡이고 budget 소진(``iteration >= max_iterations``) → ``end_faithfulness``
       (fail_faithfulness). report 부재(None)도 미충실로 간주.
    """
    f = state.faithfulness
    if f is not None and f.faithful:
        return "end_success"
    if state.iteration >= state.max_iterations:
        return "end_faithfulness"
    return "regen"


QADecision = Literal["end_success", "end_qa"]


def route_after_qa(state: V2State) -> QADecision:
    """QA aggregator 후 출하 게이트 (M5 step3, RFC N11).

    ``qa_report.overall_pass`` 만 출하 — report 부재/실패는 ``end_qa``(fail_qa).
    back-route(실패 kind 별 스테이지 재진입)는 후속 step — 단발 게이트로 시작.
    """
    r = state.qa_report
    if r is not None and r.overall_pass:
        return "end_success"
    return "end_qa"
