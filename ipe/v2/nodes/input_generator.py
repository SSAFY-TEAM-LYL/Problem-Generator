"""input_generator 노드 — GeneratorContract + io_schema → pending TestSuite (M4 step3).

deterministic 엔진(``generation.input_gen``)을 감싸는 노드. **LLM 없음** — frozen
generator_contract(step2 LLM 설계) + blueprint.io_schema 로부터 입력을 결정론 생성한다.
expected 는 None(pending) — suite assembler(step4)가 verified golden 으로 채운다.

seed: ``contract.determinism_seed`` 가 있으면 그것, 없으면 run_id 파생(재현가능).
"""

from __future__ import annotations

from collections.abc import Callable

from ipe.v1.schema import TestSuite

from ..generation.input_gen import generate_inputs, seed_from_run_id
from ..state import V2State


def make_input_generator_node() -> Callable[[V2State], V2State]:
    """factory — generator_contract + blueprint → pending TestSuite (state.test_suite).

    LLM 의존 없음 (결정론). assembler(step4)가 expected 채우기 전까지 is_assembled=False.
    """

    def node(state: V2State) -> V2State:
        contract = state.generator_contract
        bp = state.blueprint
        if contract is None or bp is None:
            msg = (
                "input_generator requires state.generator_contract and state.blueprint"
            )
            raise ValueError(msg)
        seed = (
            contract.determinism_seed
            if contract.determinism_seed is not None
            else seed_from_run_id(state.run_id)
        )
        cases = generate_inputs(contract, bp.io_schema, seed=seed)
        suite = TestSuite(cases=cases, golden_origin=None)
        return state.model_copy(update={"test_suite": suite})

    return node
