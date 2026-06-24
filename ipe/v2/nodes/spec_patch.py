"""spec_patch 노드 — revise 된 narrative 를 spec 에 반영 (B back-route).

LLM 없음. QA fail → narrative revise(faithfulness 통과) 후, narrative 가 저작한
**description(=scenario)+title 을** 새 narrative 로 교체한다. io_contract(step6
canonical 동결 렌더)/샘플/target_algorithm 은 보존 — verified golden·verification·
test_suite 가 그대로 유효하므로 synthesis 를 재실행하지 않는 싼 back-route 가
성립한다 (지문↔계약 모순류 QA 지적은 지문 쪽을 고치는 게 방향: 계약·채점셋이 진실원천).

title 도 patch 하는 이유(Phase 4): spec_bridge 가 순수 투영으로 강등되며
``spec.title = narrative.title`` 로 결합됐다 — narrative_revise 가 새 title 을 내면
spec.title 도 따라가야 재리뷰가 stale title 을 보지 않는다(단일소스 일관).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..state import V2State


def make_spec_patch_node() -> Callable[[V2State], dict[str, Any]]:
    """factory — ``spec.{description,title} := narrative.{scenario,title}`` (partial dict).

    title 도 patch: Phase 4 에서 ``spec.title = narrative.title`` 로 결합됐으므로
    revise 된 narrative 의 title 을 함께 반영해야 재리뷰가 stale title 을 안 본다.
    """

    def node(state: V2State) -> dict[str, Any]:
        if state.spec is None:
            msg = "spec_patch requires state.spec — synthesis must run first"
            raise ValueError(msg)
        if state.narrative is None:
            msg = "spec_patch requires state.narrative — revise must run first"
            raise ValueError(msg)
        patched = state.spec.model_copy(
            update={
                "description": state.narrative.scenario,
                "title": state.narrative.title,
            }
        )
        return {"spec": patched}

    return node
