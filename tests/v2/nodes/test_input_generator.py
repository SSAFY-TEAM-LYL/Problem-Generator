"""input_generator 노드 단위 테스트 (Phase 3 M4 step3).

- ``make_input_generator_node`` (LLM 없음): generator_contract + blueprint.io_schema →
  pending TestSuite(state.test_suite). expected=None(assembler 전), run_id 결정론.
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
    TestSuite,
)
from ipe.v2.nodes import make_input_generator_node
from ipe.v2.state import V2State, initial_v2_state


def _blueprint() -> ProblemBlueprint:
    return ProblemBlueprint(
        reduction_core=TargetAlgorithm.SORT,
        domain="logistics",
        io_schema=IOSchema(
            inputs=(
                IOFieldSpec(
                    name="arr",
                    type="int_array",
                    size_range=ConstraintRange(name="arr", min_value=1, max_value=20),
                    value_range=ConstraintRange(name="v", min_value=0, max_value=9),
                ),
            ),
            output_type="int_array",
            output_format="정렬된 배열",
        ),
    )


def _contract() -> GeneratorContract:
    return GeneratorContract(
        scale_families=(
            ScaleFamily(name="small", case_count=3),
            ScaleFamily(name="stress", case_count=2),
        ),
        edge_cases=(EdgeCaseSpec(name="single"),),
    )  # total_planned_cases = 6


def _state(
    *, run_id: str = "run-v2", with_contract: bool = True, with_blueprint: bool = True
) -> V2State:
    base = initial_v2_state(run_id, TargetAlgorithm.SORT)
    update: dict[str, object] = {}
    if with_blueprint:
        update["blueprint"] = _blueprint()
    if with_contract:
        update["generator_contract"] = _contract()
    return base.model_copy(update=update)


def test_node_populates_pending_test_suite() -> None:
    out = make_input_generator_node()(_state())
    suite = out.test_suite
    assert isinstance(suite, TestSuite)
    assert suite.is_assembled is False  # expected pending
    assert all(c.expected_output is None for c in suite.cases)
    assert suite.golden_origin is None


def test_node_case_count_matches_contract() -> None:
    out = make_input_generator_node()(_state())
    assert out.test_suite is not None
    assert len(out.test_suite.cases) == _contract().total_planned_cases  # 6


def test_node_deterministic_by_run_id() -> None:
    o1 = make_input_generator_node()(_state(run_id="abc"))
    o2 = make_input_generator_node()(_state(run_id="abc"))
    assert o1.test_suite is not None and o2.test_suite is not None
    texts1 = [c.input_text for c in o1.test_suite.cases]
    texts2 = [c.input_text for c in o2.test_suite.cases]
    assert texts1 == texts2  # 같은 run_id → 같은 입력


def test_node_requires_contract_and_blueprint() -> None:
    node = make_input_generator_node()
    with pytest.raises(ValueError, match="generator_contract"):
        node(_state(with_contract=False))
    with pytest.raises(ValueError, match="blueprint"):
        node(_state(with_blueprint=False))


def test_node_preserves_original_state() -> None:
    state = _state()
    out = make_input_generator_node()(state)
    assert state.test_suite is None  # 원본 불변
    assert out.test_suite is not None
    assert out.generator_contract is state.generator_contract  # 다른 채널 보존
