"""v2 modeling-layer 그래프 통합테스트 (Phase 3 M3 step5).

mock strategist/formalizer/narrative/faithfulness LLM 으로 end-to-end 검증:
1. success: faithful=True 1회 → end_success, 모든 모델링 아티팩트 populate.
2. 재생성 루프: faithful=False→True → regen 경유 success, iteration 증가.
3. budget 소진: faithful 계속 False → max_iterations 도달 → fail_faithfulness.
4. hidden 플래그가 narrative 로 전파.
"""

from __future__ import annotations

from typing import Any

from ipe.v1.schema import (
    BlueprintFormalization,
    IOFieldSpec,
    IOSchema,
    NarrativeDraft,
    NarrativeFaithfulnessReport,
    OutputInvariant,
    StrategySeed,
    TargetAlgorithm,
)
from ipe.v2.graph import build_v2_graph
from ipe.v2.state import V2State, initial_v2_state


def _seed() -> StrategySeed:
    return StrategySeed(
        reduction_core=TargetAlgorithm.DIJKSTRA,
        composition=(TargetAlgorithm.BINARY_SEARCH,),
        domain="logistics",
    )


def _formalization() -> BlueprintFormalization:
    return BlueprintFormalization(
        io_schema=IOSchema(
            inputs=(IOFieldSpec(name="N", type="int"),),
            output_type="int",
            output_format="단일 정수",
        ),
        output_invariants=(
            OutputInvariant(kind="non_negative", description="음수 불가"),
        ),
    )


class _FixedStrategistLLM:
    def seed(self, state: V2State) -> StrategySeed:
        return _seed()


class _FixedFormalizerLLM:
    def formalize(self, state: V2State) -> BlueprintFormalization:
        return _formalization()


class _RecordingNarrativeLLM:
    def __init__(self) -> None:
        self.calls = 0
        self.last_hidden: bool | None = None

    def render(self, state: V2State, *, hidden: bool) -> NarrativeDraft:
        self.calls += 1
        self.last_hidden = hidden
        return NarrativeDraft(scenario=f"시나리오 v{self.calls}")


class _ScriptedFaithfulnessLLM:
    """faithful 값 시퀀스를 순서대로 반환 (소진 시 마지막 값 반복)."""

    def __init__(self, faithful_seq: list[bool]) -> None:
        self._seq = list(faithful_seq)
        self.calls = 0

    def assess(self, state: V2State) -> NarrativeFaithfulnessReport:
        val = self._seq[min(self.calls, len(self._seq) - 1)]
        self.calls += 1
        return NarrativeFaithfulnessReport(
            faithful=val, distortions=() if val else ("왜곡 근거",)
        )


def _final(raw: Any) -> V2State:
    return raw if isinstance(raw, V2State) else V2State.model_validate(raw)


def _graph(
    *, faithful_seq: list[bool], narrative_llm: Any = None, hidden: bool = True
) -> Any:
    return build_v2_graph(
        strategist_llm=_FixedStrategistLLM(),
        formalizer_llm=_FixedFormalizerLLM(),
        narrative_llm=(
            narrative_llm if narrative_llm is not None else _RecordingNarrativeLLM()
        ),
        faithfulness_llm=_ScriptedFaithfulnessLLM(faithful_seq),
        hidden=hidden,
    )


# ---------- 1. success (faithful 1회) ----------


def test_v2_graph_success_populates_all_artifacts() -> None:
    graph = _graph(faithful_seq=[True])
    final = _final(graph.invoke(initial_v2_state("run-ok", TargetAlgorithm.DIJKSTRA)))

    assert final.final_status == "success"
    assert final.strategy is not None
    assert final.strategy.reduction_core is TargetAlgorithm.DIJKSTRA
    assert final.blueprint is not None
    assert final.blueprint.domain == "logistics"  # strategy carry-over
    assert final.narrative is not None
    assert final.faithfulness is not None
    assert final.faithfulness.faithful is True
    assert final.iteration == 0  # 재생성 없음


# ---------- 2. 재생성 루프 (False → True) ----------


def test_v2_graph_regenerates_narrative_then_succeeds() -> None:
    narrative = _RecordingNarrativeLLM()
    graph = _graph(faithful_seq=[False, True], narrative_llm=narrative)
    final = _final(
        graph.invoke(initial_v2_state("run-retry", TargetAlgorithm.DIJKSTRA))
    )

    assert final.final_status == "success"
    assert final.iteration == 1  # regen 1회
    assert narrative.calls == 2  # 최초 + 재생성
    assert final.faithfulness is not None
    assert final.faithfulness.faithful is True


# ---------- 3. budget 소진 → fail_faithfulness ----------


def test_v2_graph_exhausts_budget_when_always_unfaithful() -> None:
    graph = _graph(faithful_seq=[False])  # 항상 왜곡
    final = _final(
        graph.invoke(
            initial_v2_state("run-fail", TargetAlgorithm.DIJKSTRA, max_iterations=2)
        )
    )

    assert final.final_status == "fail_faithfulness"
    assert final.iteration == 2  # max_iterations 도달
    assert final.faithfulness is not None
    assert final.faithfulness.faithful is False


# ---------- 4. hidden 플래그 전파 ----------


def test_v2_graph_hidden_flag_propagates_to_narrative() -> None:
    narrative = _RecordingNarrativeLLM()
    graph = _graph(faithful_seq=[True], narrative_llm=narrative, hidden=False)
    final = _final(
        graph.invoke(initial_v2_state("run-direct", TargetAlgorithm.DIJKSTRA))
    )

    assert narrative.last_hidden is False
    assert final.narrative is not None
    assert final.narrative.hidden is False  # 노드가 graph config 스탬프
