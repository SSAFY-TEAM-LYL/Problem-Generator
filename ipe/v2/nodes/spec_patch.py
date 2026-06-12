"""spec_patch 노드 — revise 된 narrative 를 spec.description 에 반영 (B back-route).

LLM 없음. QA fail → narrative revise(faithfulness 통과) 후, **description 만**
새 scenario 로 교체한다. io_contract(step6 canonical 동결 렌더)/샘플/title/
target_algorithm 은 보존 — verified golden·verification·test_suite 가 그대로
유효하므로 synthesis 를 재실행하지 않는 싼 back-route 가 성립한다 (지문↔계약
모순류 QA 지적은 지문 쪽을 고치는 게 방향: 계약·채점셋이 진실원천).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..state import V2State


def make_spec_patch_node() -> Callable[[V2State], dict[str, Any]]:
    """factory — ``spec.description := narrative.scenario`` (partial dict)."""

    def node(state: V2State) -> dict[str, Any]:
        if state.spec is None:
            msg = "spec_patch requires state.spec — synthesis must run first"
            raise ValueError(msg)
        if state.narrative is None:
            msg = "spec_patch requires state.narrative — revise must run first"
            raise ValueError(msg)
        patched = state.spec.model_copy(
            update={"description": state.narrative.scenario}
        )
        return {"spec": patched}

    return node
