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
