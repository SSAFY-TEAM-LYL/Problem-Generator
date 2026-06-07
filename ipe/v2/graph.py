"""v2 modeling-layer LangGraph builder (Phase 3 M3 step5).

blueprint-first **은닉 모델링** 파이프라인을 배선한다::

    START → strategist → formalizer → narrative → faithfulness → route ─┬─ end_success
              (시드)      (FREEZE)     (은닉 렌더)   (round-trip)         │   (success)
                                          ▲                              ├─ regen → narrative
                                          └──────────────────────────────┘  (faithful=False,
                                                                              budget 남음)
                                       route(budget 소진) ── end_faithfulness (fail_faithfulness)

핵심 의도:
- M3 의 4 모델링 노드(strategist/formalizer/narrative/faithfulness)를 하나의 runnable
  그래프로. **faithful=False → narrative 재생성**(싼 반복, ``max_iterations`` 바운드).
  왜곡(distortion)만 reject 하고 은닉(omission)은 통과 — faithfulness 노드 책임.
- ``regen`` 은 iteration++ 만 하는 최소 노드 (재시도 budget 카운터). v1 ``_record``
  패턴 축약 — 본 layer 는 signature oscillation 대신 iteration cap 으로만 바운드.
- 모든 LLM 은 build 시 주입 (test 는 mock 으로 결정론 시나리오 재현). ``hidden`` 은
  narrative 렌더 모드(graph-time): True=B2B 은닉 / False=B2C 직접.

범위 (step5): **모델링 layer 만**. synthesis(golden/brute fan-out)+verification 통합은
``blueprint → spec`` 파생 브리지가 필요한 별도 작업 — v1 full mode(M2) 재사용으로 이연
(follow-up). ``state.spec``/``candidates``/``verification`` 채널은 이 그래프에서 미사용.

recursion 주의: 루프 1회 = narrative+faithfulness+regen(3 step). langgraph 기본
recursion_limit=25 → ``max_iterations`` 가 크면(>~7) invoke 시 ``config={"recursion_
limit": N}`` 로 상향 필요. 모델링 재시도 budget 은 보통 작게(<=5) 둔다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from langgraph.graph import END, StateGraph

from .nodes import (
    FaithfulnessLLM,
    FormalizerLLM,
    NarrativeLLM,
    StrategistLLM,
    make_faithfulness_node,
    make_formalizer_node,
    make_narrative_node,
    make_strategist_node,
)
from .router import route_after_faithfulness
from .state import V2FinalStatus, V2State

if TYPE_CHECKING:
    from collections.abc import Callable

    from langgraph.graph.state import CompiledStateGraph


def _bump_iteration(state: V2State) -> V2State:
    """regen 노드 — faithfulness 실패 후 재시도 카운터 증가 (narrative 재생성 전)."""
    return state.model_copy(update={"iteration": state.iteration + 1})


def _make_finalizer(status: V2FinalStatus) -> Callable[[V2State], V2State]:
    """terminal 노드 팩토리 — final_status set 후 END."""

    def node(state: V2State) -> V2State:
        return state.model_copy(update={"final_status": status})

    return node


def build_v2_graph(
    *,
    strategist_llm: StrategistLLM | None = None,
    formalizer_llm: FormalizerLLM | None = None,
    narrative_llm: NarrativeLLM | None = None,
    faithfulness_llm: FaithfulnessLLM | None = None,
    hidden: bool = True,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """v2 은닉 모델링 그래프 빌드. None dependency 는 production default(Anthropic).

    ``hidden`` = narrative 렌더 모드 (True=B2B 은닉 기본). test 는 모든 LLM mock 주입.
    """
    builder: StateGraph = StateGraph(V2State)  # type: ignore[type-arg]

    builder.add_node("strategist", cast(Any, make_strategist_node(strategist_llm)))
    builder.add_node("formalizer", cast(Any, make_formalizer_node(formalizer_llm)))
    builder.add_node(
        "narrative", cast(Any, make_narrative_node(narrative_llm, hidden=hidden))
    )
    builder.add_node(
        "faithfulness", cast(Any, make_faithfulness_node(faithfulness_llm))
    )
    builder.add_node("regen", cast(Any, _bump_iteration))
    builder.add_node("end_success", cast(Any, _make_finalizer("success")))
    builder.add_node(
        "end_faithfulness", cast(Any, _make_finalizer("fail_faithfulness"))
    )

    builder.set_entry_point("strategist")
    builder.add_edge("strategist", "formalizer")
    builder.add_edge("formalizer", "narrative")
    builder.add_edge("narrative", "faithfulness")
    builder.add_conditional_edges(
        "faithfulness",
        route_after_faithfulness,
        cast(
            Any,
            {
                "end_success": "end_success",
                "regen": "regen",
                "end_faithfulness": "end_faithfulness",
            },
        ),
    )
    builder.add_edge("regen", "narrative")  # 재생성 루프
    builder.add_edge("end_success", END)
    builder.add_edge("end_faithfulness", END)

    return builder.compile()
