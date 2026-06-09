"""generator_designer 노드 단위 테스트 (Phase 3 M4 step2).

- ``make_generator_designer_node``: frozen blueprint → GeneratorContract
  (state.generator_contract). LLM 이 scale_families/edge_cases 저작 (생성 전략 = 새
  설계라 carry-over 없음). 입력 *생성* 자체는 결정론(step3).

mock LLM 으로 sandbox/네트워크 없이 결정론 검증.
"""

from __future__ import annotations

import pytest

from ipe.v1.schema import (
    ConstraintRange,
    EdgeCaseSpec,
    GeneratorContract,
    IOFieldSpec,
    IOSchema,
    ProblemBlueprint,
    ScaleFamily,
    TargetAlgorithm,
)
from ipe.v2.nodes import make_generator_designer_node
from ipe.v2.state import V2State, initial_v2_state


def _blueprint() -> ProblemBlueprint:
    return ProblemBlueprint(
        reduction_core=TargetAlgorithm.DIJKSTRA,
        domain="logistics",
        io_schema=IOSchema(
            inputs=(
                IOFieldSpec(
                    name="N",
                    type="int",
                    value_range=ConstraintRange(name="N", min_value=1, max_value=100000),
                ),
            ),
            output_type="int",
            output_format="단일 정수",
        ),
    )


def _contract() -> GeneratorContract:
    return GeneratorContract(
        scale_families=(
            ScaleFamily(
                name="small",
                case_count=3,
                field_bounds=(ConstraintRange(name="N", min_value=1, max_value=10),),
            ),
            ScaleFamily(name="stress", case_count=2),
        ),
        edge_cases=(EdgeCaseSpec(name="single", description="N=1"),),
    )


def _state(*, with_blueprint: bool = True) -> V2State:
    base = initial_v2_state("run-v2", TargetAlgorithm.DIJKSTRA)
    if with_blueprint:
        return base.model_copy(update={"blueprint": _blueprint()})
    return base


class _FixedGeneratorDesignerLLM:
    def __init__(self, contract: GeneratorContract) -> None:
        self._contract = contract

    def design(self, state: V2State) -> GeneratorContract:
        return self._contract


def test_generator_designer_populates_contract() -> None:
    out = make_generator_designer_node(_FixedGeneratorDesignerLLM(_contract()))(
        _state()
    )

    contract = out.generator_contract
    assert isinstance(contract, GeneratorContract)
    assert len(contract.scale_families) == 2
    assert contract.scale_families[0].name == "small"
    assert len(contract.edge_cases) == 1
    assert contract.total_planned_cases == 6  # 3 + 2 + 1 edge


def test_generator_designer_requires_blueprint() -> None:
    bare = _state(with_blueprint=False)
    node = make_generator_designer_node(_FixedGeneratorDesignerLLM(_contract()))
    with pytest.raises(ValueError, match="blueprint"):
        node(bare)


def test_generator_designer_preserves_original_state() -> None:
    state = _state()
    out = make_generator_designer_node(_FixedGeneratorDesignerLLM(_contract()))(state)
    assert state.generator_contract is None  # 원본 불변
    assert out.generator_contract is not None
    assert out.blueprint is state.blueprint  # 다른 채널 보존
