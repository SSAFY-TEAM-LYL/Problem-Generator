"""LangGraph 빌더 — P4 단계는 직선 edge skeleton만.

스펙: ARCHITECTURE.md §3.4 (LangGraph 빌더)

P4 (현재):
    START → architect → coder → executor → END (직선)

P7 (예정):
    add_conditional_edges로 route_after_executor 추가 — 실패 시 architect/coder/halt 분기
P8 (예정):
    SqliteSaver checkpointer 주입
P9 (예정):
    evaluator 노드 추가 (success 분기)

노드 의존성 (LLMCallTracker, SandboxedRunner)은 ``functools.partial``로
keyword-only로 주입한다. LangGraph는 노드 함수를 ``(state) -> state``로 호출하므로
partial이 이미 tracker/runner를 bind한 callable을 등록하면 시그니처가 맞는다.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from ipe.nodes import architect, coder, executor
from ipe.observability import LLMCallTracker
from ipe.sandbox.runner import SandboxedRunner
from ipe.state import ProblemState


def build_graph(
    *,
    tracker: LLMCallTracker,
    runner: SandboxedRunner,
    workdir_root: Path | None = None,
) -> Any:
    """직선 edge 그래프 빌드 — P4 minimal.

    노드:
    - architect: target_algorithm → problem + constraints + samples
    - coder:     problem → solution_code (혹은 IMPOSSIBLE → architect로)
    - executor:  solution + samples → Phase A 검증 (3-way 휴리스틱)

    P4 단계는 실패 분기를 따로 라우팅하지 않고 그래프가 END로 흐른다.
    실제 사이클/재시도는 P7의 ``add_conditional_edges``에서 추가한다.
    """
    g = StateGraph(ProblemState)
    g.add_node("architect", partial(architect.run, tracker=tracker))
    g.add_node("coder", partial(coder.run, tracker=tracker))
    g.add_node(
        "executor",
        partial(executor.run, runner=runner, workdir_root=workdir_root),
    )
    g.add_edge(START, "architect")
    g.add_edge("architect", "coder")
    g.add_edge("coder", "executor")
    g.add_edge("executor", END)
    return g.compile()
