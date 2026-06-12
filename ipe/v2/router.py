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


SpecAuthoringDecision = Literal["designer", "end_spec_authoring"]


def route_after_spec_bridge(state: V2State) -> SpecAuthoringDecision:
    """spec_bridge 후 가드 분기 — LLM 저작 실패 시 valid fail 종료.

    structured output 재시도 전멸이 graph 밖 crash 로 전파되던 것(BS-run3 실측)을
    ``fail_spec_authoring`` 종료로 회수. ``spec`` populate 시에만 synthesis 진행
    (실패 사유는 ``state.spec_authoring_error`` 에 보존).
    """
    if state.spec is None:
        return "end_spec_authoring"
    return "designer"


QADecision = Literal["end_success", "routeback", "end_qa"]


def route_after_qa(state: V2State) -> QADecision:
    """QA aggregator 후 출하 게이트 + back-route (M5 RFC N11).

    1. ``qa_report.overall_pass`` → ``end_success`` (출하).
    2. fail 이고 back-route 예산 잔여(``qa_routebacks < max_qa_routebacks``) →
       ``routeback`` — narrative revise 재진입 (findings 피드백, 검증·suite 보존).
    3. fail 이고 예산 소진(또는 report 부재=집계 불능) → ``end_qa``(fail_qa).
    """
    r = state.qa_report
    if r is None:
        return "end_qa"
    if r.overall_pass:
        return "end_success"
    if state.qa_routebacks < state.max_qa_routebacks:
        return "routeback"
    return "end_qa"
