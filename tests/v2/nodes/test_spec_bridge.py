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
from ipe.v2.generation.input_parser import render_input_parser
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


def test_spec_bridge_empties_sample_expected_for_golden_fill() -> None:
    """사용자 원칙: sample expected 는 LLM 손계산 금지 — node 가 비우고 하류
    sample_filler 가 canonical golden 실행으로 채운다. LLM 이 expected 를 줘도
    input 만 살린다 (freeze 규율)."""
    out = make_spec_bridge_node(_FixedSpecBridgeLLM(_authored_spec()))(_state())

    spec = out.spec
    assert isinstance(spec, ProblemSpec)
    assert [s.input_text for s in spec.sample_testcases] == ["3", "4", "5"]  # input 유지
    assert all(s.expected_output == "" for s in spec.sample_testcases)  # expected 비움


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


def test_spec_bridge_freezes_input_parser_code_from_io_schema() -> None:
    """#2: stdin 파서도 코드로 freeze — io_schema 에서 render_input_parser 로 파생.

    synthesis 코더가 LLM 파서를 직접 쓰지 않고 이 preamble 을 받아 파서 분산(IndexError·
    중복카운트 오독)을 구조적으로 차단한다."""
    out = make_spec_bridge_node(_FixedSpecBridgeLLM(_authored_spec()))(_state())

    spec = out.spec
    assert isinstance(spec, ProblemSpec)
    assert spec.input_parser_code == render_input_parser(_blueprint().io_schema)
    assert spec.input_parser_code  # 비어있지 않음 (v2 는 항상 주입)


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


# ---------- LLM 저작 실패 가드 (BS-run3 실측 crash 대응) ----------


class _RaisingSpecBridgeLLM:
    """structured output 5-retry 전멸을 모사 — author() 가 예외를 던진다."""

    def author(self, state: V2State) -> ProblemSpec:
        msg = "structured output 거부 — io_contract 가 string"
        raise RuntimeError(msg)


def test_spec_bridge_llm_failure_records_error_without_crash() -> None:
    """LLM 저작 실패(BS-run3: ValidationError 5-retry 전멸이 graph 밖 crash 로
    전파)가 노드 가드로 회수 — spec=None 유지 + spec_authoring_error 에 예외
    요약 기록 (silent swallow 금지, 라우터가 fail_spec_authoring 으로 종료)."""
    out = make_spec_bridge_node(_RaisingSpecBridgeLLM())(_state())

    assert out.spec is None
    assert out.spec_authoring_error is not None
    assert "RuntimeError" in out.spec_authoring_error
    assert "structured output" in out.spec_authoring_error


def test_spec_bridge_precondition_violation_still_raises() -> None:
    """blueprint/narrative 부재는 LLM 신뢰성이 아니라 배선 버그 — 가드 대상이
    아니며 기존대로 즉시 raise (오류 은폐 방지)."""
    bare = _state(with_blueprint=False)
    node = make_spec_bridge_node(_RaisingSpecBridgeLLM())
    with pytest.raises(ValueError, match="blueprint"):
        node(bare)
