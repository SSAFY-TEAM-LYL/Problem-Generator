"""병렬 Solution Synthesis 서브그래프 (Phase 3 M2 step3).

flow::

    START → dispatch ─┬─→ golden_0 ─┐
                      ├─→ golden_1 ─┤
                      ├─→  ...      ├─→ reconciler → END
                      └─→ brute  ───┘
                      └─ fan-out ─┘     └─ fan-in ─┘

- ``dispatch``: fan-out trigger — state 무변경 (partial ``{}`` 반환).
- ``golden_i`` / ``brute``: ``make_synthesis_coder_node`` — 각자 ``SolutionCandidate``
  를 ``candidates`` reducer 채널에 append (partial dict 반환, M0 스파이크 패턴).
- ``reconciler``: 모든 병렬 노드 완료 후 **1회** fan-in — ``reconcile()`` 로
  canonical 채택 → ``state.reconciliation``.

이 서브그래프는 step3 단위로 **독립** — 메인 ``build_graph()`` 배선(compat flag
``mode: full``)은 step4. golden 들은 origin 다른 ``CoderLLM`` 으로 주입 (differential
독립성 전제 §7.4). 모든 LLM/runner 주입 가능 — 통합 테스트는 mock 으로 결정론 재현.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from langgraph.graph import END, START, StateGraph

from .nodes.coder import CoderLLM
from .nodes.reconciler import make_reconciler_node
from .nodes.synthesis_coder import make_synthesis_coder_node
from .state import V1State
from .verification._exec import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIME_LIMIT_MS,
    CodeRunner,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


def _dispatch(_state: V1State) -> dict[str, Any]:
    """fan-out trigger — state 무변경 (빈 partial dict)."""
    return {}


def build_synthesis_graph(
    *,
    golden_llms: Sequence[CoderLLM],
    brute_llm: CoderLLM,
    runner: CodeRunner,
    golden_origins: Sequence[str] | None = None,
    brute_origin: str = "naive",
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """fan-out(golden×K + brute) → fan-in(reconciler) 서브그래프 빌드.

    ``golden_llms`` 길이 K = golden fan-out 폭. 각 golden 의 ``origin`` 은
    ``golden_origins`` (없으면 ``golden-0..K-1``), ``fanout_index`` 는 enumerate
    순서 — reconcile 의 reference 는 최소 index(golden_0)로 결정론. brute 는 단일.
    """
    if not golden_llms:
        msg = "build_synthesis_graph 는 golden LLM 이 최소 1개 필요"
        raise ValueError(msg)
    origins = (
        list(golden_origins)
        if golden_origins is not None
        else [f"golden-{i}" for i in range(len(golden_llms))]
    )
    if len(origins) != len(golden_llms):
        msg = (
            f"golden_origins 길이({len(origins)}) != golden_llms({len(golden_llms)})"
        )
        raise ValueError(msg)

    builder: StateGraph = StateGraph(V1State)  # type: ignore[type-arg]
    # graph.py 와 동일 cast(Any) 우회 — wrap된 Callable 이 NodeInputT generic 과
    # 직접 매칭 안 됨.
    builder.add_node("dispatch", cast(Any, _dispatch))

    golden_names: list[str] = []
    for i, (llm, origin) in enumerate(zip(golden_llms, origins, strict=True)):
        name = f"golden_{i}"
        golden_names.append(name)
        builder.add_node(
            name,
            cast(
                Any,
                make_synthesis_coder_node(
                    llm, role="golden", origin=origin, fanout_index=i
                ),
            ),
        )
    builder.add_node(
        "brute",
        cast(
            Any,
            make_synthesis_coder_node(
                brute_llm, role="brute", origin=brute_origin, fanout_index=0
            ),
        ),
    )
    builder.add_node(
        "reconciler",
        cast(
            Any,
            make_reconciler_node(
                runner, time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb
            ),
        ),
    )

    builder.add_edge(START, "dispatch")
    for name in (*golden_names, "brute"):
        builder.add_edge("dispatch", name)  # fan-out (parallel superstep)
        builder.add_edge(name, "reconciler")  # fan-in (join once)
    builder.add_edge("reconciler", END)
    return builder.compile()
