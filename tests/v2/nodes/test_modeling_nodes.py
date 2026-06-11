"""Strategist / Formalizer 노드 단위 테스트 (Phase 3 M3 step2, blueprint-first).

- ``make_strategist_node``: seed_algorithm hint → StrategySeed (state.strategy).
- ``make_formalizer_node``: frozen StrategySeed → ProblemBlueprint freeze
  (state.blueprint). 알고리즘 필드는 strategy 에서 carry-over (freeze 규율 — Formalizer
  LLM 은 형식 면만 산출하므로 은닉 코어를 못 바꾼다).

mock LLM 으로 sandbox/네트워크 없이 결정론 검증 (v1 test_synthesis_nodes 패턴 미러).
"""

from __future__ import annotations

import pytest

from ipe.v1.schema import (
    BlueprintFormalization,
    IOFieldSpec,
    IOSchema,
    OutputInvariant,
    ProblemBlueprint,
    StrategySeed,
    TargetAlgorithm,
)
from ipe.v2.nodes import make_formalizer_node, make_strategist_node
from ipe.v2.state import V2State, initial_v2_state


def _seed() -> StrategySeed:
    return StrategySeed(
        reduction_core=TargetAlgorithm.DIJKSTRA,
        composition=(TargetAlgorithm.BINARY_SEARCH,),
        domain="logistics",
        rationale="배송 경로를 최단경로로 위장",
    )


def _formalization() -> BlueprintFormalization:
    return BlueprintFormalization(
        io_schema=IOSchema(
            inputs=(IOFieldSpec(name="N", type="int"),),
            output_type="int",
            output_format="단일 정수",
        ),
        output_invariants=(
            OutputInvariant(kind="non_negative", description="거리는 음수 불가"),
        ),
    )


class _FixedStrategistLLM:
    """고정 StrategySeed 를 반환하는 mock (state 무시)."""

    def __init__(self, seed: StrategySeed) -> None:
        self._seed = seed

    def seed(self, state: V2State) -> StrategySeed:
        return self._seed


class _FixedFormalizerLLM:
    """고정 BlueprintFormalization 을 반환하는 mock (state 무시)."""

    def __init__(self, formalization: BlueprintFormalization) -> None:
        self._formalization = formalization

    def formalize(self, state: V2State) -> BlueprintFormalization:
        return self._formalization


# ---------- strategist ----------


def test_strategist_populates_strategy() -> None:
    state = initial_v2_state("run-v2", TargetAlgorithm.DIJKSTRA)
    out = make_strategist_node(_FixedStrategistLLM(_seed()))(state)

    assert out.strategy is not None
    assert out.strategy == _seed()
    assert out.strategy.reduction_core is TargetAlgorithm.DIJKSTRA
    assert out.strategy.domain == "logistics"
    # 원본 불변 + blueprint 는 아직 미생성
    assert state.strategy is None
    assert out.blueprint is None
    assert out.run_id == "run-v2"


# ---------- formalizer ----------


def test_formalizer_freezes_blueprint_from_strategy() -> None:
    seeded = initial_v2_state("run-v2", TargetAlgorithm.DIJKSTRA).model_copy(
        update={"strategy": _seed()}
    )
    out = make_formalizer_node(_FixedFormalizerLLM(_formalization()))(seeded)

    bp = out.blueprint
    assert isinstance(bp, ProblemBlueprint)
    # 알고리즘 결정 필드는 strategy 에서 carry-over (Formalizer 가 못 바꿈)
    assert bp.reduction_core is TargetAlgorithm.DIJKSTRA
    assert bp.composition == (TargetAlgorithm.BINARY_SEARCH,)
    assert bp.domain == "logistics"
    # 형식 면은 Formalizer LLM 산출
    assert bp.io_schema.output_type == "int"
    assert bp.output_invariants[0].kind == "non_negative"


def test_formalizer_carry_over_is_authoritative_over_llm() -> None:
    """Formalizer LLM 은 형식만 산출 → 알고리즘 필드는 strategy 가 authoritative."""
    seed = StrategySeed(reduction_core=TargetAlgorithm.KNAPSACK, domain="warehouse")
    seeded = initial_v2_state("r", TargetAlgorithm.KNAPSACK).model_copy(
        update={"strategy": seed}
    )
    out = make_formalizer_node(_FixedFormalizerLLM(_formalization()))(seeded)

    bp = out.blueprint
    assert isinstance(bp, ProblemBlueprint)
    # io_schema 가 어떤 형식이든 reduction_core 는 strategy(knapsack) 그대로 유지
    assert bp.reduction_core is TargetAlgorithm.KNAPSACK
    assert bp.composition == ()  # seed 가 빈 composition → 그대로


def test_formalizer_requires_strategy() -> None:
    bare = initial_v2_state("r", TargetAlgorithm.BFS)  # strategy 없음
    node = make_formalizer_node(_FixedFormalizerLLM(_formalization()))
    with pytest.raises(ValueError, match="strategy"):
        node(bare)


# ---------- composition (strategist → formalizer) ----------


def test_strategist_then_formalizer_compose() -> None:
    state = initial_v2_state("run-v2", TargetAlgorithm.DIJKSTRA)
    s_node = make_strategist_node(_FixedStrategistLLM(_seed()))
    f_node = make_formalizer_node(_FixedFormalizerLLM(_formalization()))

    after = f_node(s_node(state))

    assert after.strategy is not None
    assert after.blueprint is not None
    # blueprint 의 알고리즘 필드 == strategy 의 것 (freeze carry-over)
    assert after.blueprint.reduction_core is after.strategy.reduction_core
    assert after.blueprint.domain == after.strategy.domain


# ---------- prompt 규율 ----------


def test_strategist_prompt_lists_all_valid_algorithms() -> None:
    """composition/reduction_core 허용 enum 값이 prompt 에 전부 명시 — 모델이
    'greedy' 같은 목록 밖 기법을 emit 해 structured output 이 거부되는 것 방지
    (M4 step5 e2e 실측 발견). enum 확장 시 자동 동기화 검증."""
    from ipe.v2.nodes.strategist import _SYSTEM_PROMPT

    for algo in TargetAlgorithm:
        assert algo.value in _SYSTEM_PROMPT


def test_narrative_prompt_forbids_format_prose() -> None:
    """지문 형식서술 금지 규율이 system prompt 에 명시 — QA anchor 0/3 의 공통
    blocker(description 'E V'·0-indexed 서술 ↔ io_contract canonical 렌더 모순)의
    원천 차단 (생성 구조화 > 사후 게이트). 규율 문구 드리프트 방지."""
    from ipe.v2.nodes.narrative import _SYSTEM_PROMPT

    assert "인덱싱" in _SYSTEM_PROMPT  # 0-indexed/1-indexed 서술 금지
    assert "줄 구성" in _SYSTEM_PROMPT  # 입력 줄 구조/순서 서술 금지
    assert "단일 진실원천" in _SYSTEM_PROMPT  # 형식은 io_contract 렌더가 담당
    assert "예시" in _SYSTEM_PROMPT  # 구체 입력/출력 예시 블록 금지 (샘플이 담당)


def test_formalizer_prompt_forbids_orphan_fields() -> None:
    """io_schema 필드 간 의미 정합 규율이 system prompt 에 명시 — A-후 QA 재측정
    run3 blocker(capacity_threshold 고아 필드: 비교 대상 per-edge capacity 가
    io_schema 에 없어 풀 수 없는 문제)의 원천 차단. 규율 문구 드리프트 방지."""
    from ipe.v2.nodes.formalizer import _SYSTEM_PROMPT

    assert "고아 필드" in _SYSTEM_PROMPT  # 참조 대상 없는 필드 금지
    assert "비교 대상" in _SYSTEM_PROMPT  # 임계값류는 per-element 데이터 필요
    assert "의미 정합" in _SYSTEM_PROMPT  # 필드 집합의 자기완결성


def test_faithfulness_prompt_rejects_absent_data_mechanics() -> None:
    """'지문이 계약에 없는 데이터를 요구하는 메커니즘 = 왜곡' 규율이 system prompt
    에 명시 — run3 에서 faithfulness 가 고아 필드 지문을 통과시킨 검출 한계 보강
    (은닉=누락 OK 의 역방향: 계약보다 *많은* 입력 전제는 reject). 드리프트 방지."""
    from ipe.v2.nodes.faithfulness import _SYSTEM_PROMPT

    assert "없는 데이터" in _SYSTEM_PROMPT  # 계약 밖 데이터 요구 메커니즘
    assert "풀 수 없" in _SYSTEM_PROMPT  # 주어진 입력만으로 불가 = 왜곡 근거
