"""M0 스파이크 — 병렬 fan-out → fan-in + reducer 채널 선검증 (Phase 3 RFC R3).

목적: v2 의 병렬 영역(solution synth / verification / test-gen / QA)이
실제로 작동하려면, **여러 병렬 노드가 한 state 채널에 동시에 write → aggregator
가 fan-in 에서 읽는** 패턴이 LangGraph + 현재의 Pydantic typed state 에서
성립해야 한다. 이 스파이크가 답하는 구체 질문:

- Q1. frozen=True + extra="forbid" (V1State 와 동일 config) Pydantic state 에서
      reducer 채널(Annotated[list, operator.add])이 작동하나?
- Q2. fan-out → K 병렬 노드 → fan-in aggregator 가 결과를 결정론적으로 누적/집계하나?
- Q3. 노드 반환 스타일 — 병렬 노드는 partial dict({"results":[x]})를 반환해야
      reducer 가 merge 한다 (전체 model_copy 면 overwrite 위험).

이 파일은 production import surface 를 건드리지 않는 **독립 실험**이다. M2(병렬
solution synth) 설계의 레퍼런스.

발견(2026-06-01, langgraph 1.2.2):
- (테스트 통과 시) frozen Pydantic + reducer OK, partial-dict 반환으로 누적,
  aggregator 는 모든 병렬 노드 완료 후 1회 join.
- 병렬 노드 실행 순서는 보장되지 않음 → aggregator 는 order-independent 여야 함
  (정렬 후 비교로 검증).
"""

from __future__ import annotations

import operator
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field


class SpikeState(BaseModel):
    """V1State 와 동일한 frozen + extra=forbid config 를 의도적으로 미러."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int
    # reducer 채널 — 병렬 노드들이 각자 append, operator.add 가 concat
    results: Annotated[list[str], operator.add] = Field(default_factory=list)
    aggregated: str | None = None


def _dispatch(_state: SpikeState) -> dict:
    """fan-out trigger — state 변경 없음 (빈 dict)."""
    return {}


def _make_worker(name: str):
    def _worker(state: SpikeState) -> dict:
        # partial dict 반환 → reducer 가 기존 results 와 merge (Q3)
        return {"results": [f"{name}:{state.seed}"]}

    return _worker


def _aggregate(state: SpikeState) -> dict:
    # 모든 병렬 결과가 모인 뒤 1회 — order-independent 집계
    return {"aggregated": "|".join(sorted(state.results))}


def _build_spike_graph():
    builder: StateGraph = StateGraph(SpikeState)
    builder.add_node("dispatch", _dispatch)
    builder.add_node("worker_a", _make_worker("a"))
    builder.add_node("worker_b", _make_worker("b"))
    builder.add_node("worker_c", _make_worker("c"))
    builder.add_node("aggregate", _aggregate)

    builder.add_edge(START, "dispatch")
    # fan-out: dispatch → 3 worker (parallel superstep)
    builder.add_edge("dispatch", "worker_a")
    builder.add_edge("dispatch", "worker_b")
    builder.add_edge("dispatch", "worker_c")
    # fan-in: 3 worker → aggregate (join, runs once after all)
    builder.add_edge("worker_a", "aggregate")
    builder.add_edge("worker_b", "aggregate")
    builder.add_edge("worker_c", "aggregate")
    builder.add_edge("aggregate", END)
    return builder.compile()


def _final(raw: object) -> SpikeState:
    """langgraph invoke 는 dict 반환 — SpikeState 로 정규화 (기존 코드 패턴)."""
    if isinstance(raw, SpikeState):
        return raw
    return SpikeState.model_validate(raw)


def test_q1_frozen_state_with_reducer_does_not_raise():
    """Q1: frozen=True + extra=forbid 에서 reducer 그래프가 예외 없이 컴파일·실행."""
    graph = _build_spike_graph()
    final = _final(graph.invoke(SpikeState(seed=7)))
    assert final is not None


def test_q2_parallel_fanin_accumulates_all_results():
    """Q2: 3 병렬 노드의 결과가 reducer 로 모두 누적 (순서 무관)."""
    graph = _build_spike_graph()
    final = _final(graph.invoke(SpikeState(seed=7)))
    assert set(final.results) == {"a:7", "b:7", "c:7"}


def test_q2_aggregator_joins_once_after_all_parallel():
    """Q2: aggregator 가 모든 병렬 완료 후 1회 — 정렬 join 이 셋 모두 포함."""
    graph = _build_spike_graph()
    final = _final(graph.invoke(SpikeState(seed=1)))
    # 1회만 돌고 셋 다 봤다면 정확히 이 문자열 (3회 돌거나 일찍 돌면 깨짐)
    assert final.aggregated == "a:1|b:1|c:1"


def test_q3_reducer_concat_is_order_independent_but_complete():
    """Q3: 여러 seed 로 반복해도 항상 완전 누적 (partial-dict 반환 패턴 검증)."""
    graph = _build_spike_graph()
    for seed in (0, 42, 999):
        final = _final(graph.invoke(SpikeState(seed=seed)))
        assert sorted(final.results) == [f"a:{seed}", f"b:{seed}", f"c:{seed}"]
