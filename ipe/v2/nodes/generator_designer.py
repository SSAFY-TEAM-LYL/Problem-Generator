"""generator_designer 노드 — frozen io_schema → GeneratorContract (순수 투영, Phase 3).

이전엔 Opus LLM 이 scale_families/edge_cases 를 저작했으나, 그 계약은 io_schema 가 이미
결정하는 정보(규모 tier·실현가능 퇴화)를 추가하지 않고 LLM 의 자유도는
``input_gen._edge_bias`` 가 5개 bias 로 접었다 — unrealizable 카테고리(self_loop·특정
위상 등)를 채점셋 이름에 남겨 형식 계약과 모순시키는 리스크(F18 reject, N=18 실측)만
더했다. 단일 IR 리팩터(RFC §4)는 이 노드를 io_schema 의 **순수 투영**으로 강등한다:
``derive_generator_contract`` 가 sized 필드 size_range 를 log-spaced scale tier 로,
실현가능 퇴화를 edge case 로 결정론 파생한다. 효과 = Opus 호출 1 삭제 + unrealizable
fail_qa → 0. 계약이 io_schema 의 함수이므로 다른 투영과 모순 불가(consistency-by-construction).
"""

from __future__ import annotations

from collections.abc import Callable

from ..generation.input_gen import derive_generator_contract
from ..state import V2State


def make_generator_designer_node() -> Callable[[V2State], V2State]:
    """factory — frozen blueprint.io_schema → GeneratorContract (순수, LLM 없음).

    formalizer 가 freeze 한 io_schema 만 보고 결정론 투영한다(carry-over 강제 불요 —
    계약은 io_schema 의 함수). validator(Phase 2)가 이미 io_schema 완전성(collection
    size_range·참조 해소)을 보장하므로 verification 통과 후 도달하는 io_schema 는 well-formed.
    """

    def node(state: V2State) -> V2State:
        bp = state.blueprint
        if bp is None:
            msg = "generator_designer requires state.blueprint — formalizer must run first"
            raise ValueError(msg)
        contract = derive_generator_contract(bp.io_schema)
        return state.model_copy(update={"generator_contract": contract})

    return node
