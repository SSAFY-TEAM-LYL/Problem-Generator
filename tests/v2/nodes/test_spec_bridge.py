"""spec_bridge 노드 단위 테스트 (Phase 3 v2 synthesis 통합 step1).

- ``make_spec_bridge_node``: blueprint + narrative → ProblemSpec (state.spec). LLM 이
  title/io_contract/constraints/sample_testcases 저작 → 노드가 target_algorithm
  (=blueprint.reduction_core) + description(=narrative.scenario) 강제 carry-over.

mock LLM 으로 sandbox/네트워크 없이 결정론 검증.
"""

from __future__ import annotations

import pytest

from ipe.v1.schema import (
    IOContract,
    IOFieldSpec,
    IOSchema,
    Narrative,
    ProblemBlueprint,
    ProblemSpec,
    SampleTestCase,
    TargetAlgorithm,
)
from ipe.v2.generation.input_gen import render_input_format
from ipe.v2.nodes import make_spec_bridge_node
from ipe.v2.state import V2State, initial_v2_state


def _blueprint() -> ProblemBlueprint:
    return ProblemBlueprint(
        reduction_core=TargetAlgorithm.DIJKSTRA,
        domain="logistics",
        io_schema=IOSchema(
            inputs=(IOFieldSpec(name="N", type="int"),),
            output_type="int",
            output_format="단일 정수",
        ),
    )


def _narrative() -> Narrative:
    return Narrative(
        scenario="물류 센터 최소 이동 비용 지문", hidden=True, domain="logistics"
    )


def _authored_spec() -> ProblemSpec:
    """LLM 이 저작한 spec — target_algorithm/description 은 일부러 '틀리게' 두어
    노드의 carry-over override 를 실증."""
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.KNAPSACK,  # 틀림 → 노드가 DIJKSTRA 로 override
        title="배송 경로 최적화",
        description="LLM 이 쓴 잘못된 설명",  # → 노드가 narrative.scenario 로 override
        io_contract=IOContract(input_format="N", output_format="정수"),
        sample_testcases=[
            SampleTestCase(input_text="3", expected_output="1"),
            SampleTestCase(input_text="4", expected_output="2"),
            SampleTestCase(input_text="5", expected_output="3"),
        ],
    )


def _state(*, with_blueprint: bool = True, with_narrative: bool = True) -> V2State:
    base = initial_v2_state("run-v2", TargetAlgorithm.DIJKSTRA)
    update: dict[str, object] = {}
    if with_blueprint:
        update["blueprint"] = _blueprint()
    if with_narrative:
        update["narrative"] = _narrative()
    return base.model_copy(update=update)


class _FixedSpecBridgeLLM:
    def __init__(self, spec: ProblemSpec) -> None:
        self._spec = spec

    def author(self, state: V2State) -> ProblemSpec:
        return self._spec


def test_spec_bridge_populates_spec_with_authored_fields() -> None:
    out = make_spec_bridge_node(_FixedSpecBridgeLLM(_authored_spec()))(_state())

    spec = out.spec
    assert isinstance(spec, ProblemSpec)
    # LLM 저작 필드
    assert spec.title == "배송 경로 최적화"
    assert len(spec.sample_testcases) == 3


def test_spec_bridge_carry_over_target_algorithm_and_description() -> None:
    """target_algorithm/description 은 blueprint/narrative 가 authoritative (override)."""
    out = make_spec_bridge_node(_FixedSpecBridgeLLM(_authored_spec()))(_state())

    spec = out.spec
    assert isinstance(spec, ProblemSpec)
    # LLM 이 KNAPSACK 을 줬어도 blueprint.reduction_core(DIJKSTRA) 로 강제
    assert spec.target_algorithm is TargetAlgorithm.DIJKSTRA
    # LLM 설명 대신 narrative.scenario 로 강제
    assert spec.description == "물류 센터 최소 이동 비용 지문"


def test_spec_bridge_freezes_io_contract_to_canonical_render() -> None:
    """io_contract 는 LLM 산출 무시 — input_format=canonical 렌더, output_format=
    io_schema carry-over (step6: 직렬화 규약↔골든 파서 정렬, ratio 0.0 해소)."""
    out = make_spec_bridge_node(_FixedSpecBridgeLLM(_authored_spec()))(_state())

    spec = out.spec
    assert isinstance(spec, ProblemSpec)
    # LLM 이 'N' 이라는 prose 를 줬어도 io_schema 에서 렌더한 canonical 로 교체
    assert spec.io_contract.input_format == render_input_format(
        _blueprint().io_schema
    )
    # output_format 은 formalizer 가 동결한 io_schema.output_format carry-over
    assert spec.io_contract.output_format == "단일 정수"


def test_spec_bridge_requires_blueprint() -> None:
    bare = _state(with_blueprint=False)
    node = make_spec_bridge_node(_FixedSpecBridgeLLM(_authored_spec()))
    with pytest.raises(ValueError, match="blueprint"):
        node(bare)


def test_spec_bridge_requires_narrative() -> None:
    bare = _state(with_narrative=False)
    node = make_spec_bridge_node(_FixedSpecBridgeLLM(_authored_spec()))
    with pytest.raises(ValueError, match="narrative"):
        node(bare)


def test_spec_bridge_preserves_original_state() -> None:
    state = _state()
    out = make_spec_bridge_node(_FixedSpecBridgeLLM(_authored_spec()))(state)
    assert state.spec is None  # 원본 불변
    assert out.spec is not None
    assert out.blueprint is state.blueprint
    assert out.narrative is state.narrative
