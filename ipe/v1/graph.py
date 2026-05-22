"""v1 LangGraph builder (D안 PR-A3).

flow::

    START → architect → designer → coder → executor → record → router →
                                                                  ├── architect
                                                                  ├── designer
                                                                  ├── coder
                                                                  ├── end_success
                                                                  ├── end_budget
                                                                  ├── end_oscillation
                                                                  └── end_schema_violation
                                                                          ↓
                                                                         END

핵심 의도:
- ``record`` 노드: executor 후 IterationContext 에 IterationRecord append +
  iteration += 1. router 가 그 결과 state 를 받아 oscillation count (현재 sig
  포함된 누적) + iteration cap 평가.
- ``router`` (router.py:route_after_executor) 가 enum/threshold 기반 결정론적
  dispatch (D안 H1).
- 4 end_* 노드는 각자 ``V1State.final_status`` 를 ``FinalStatus`` literal 로 set
  후 END.

dependency injection: graph build 시 모든 LLM/runner/verifier_getter 주입 가능 —
integration test 가 mock 으로 결정론적 시나리오 재현.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from langgraph.graph import END, StateGraph

from .nodes import (
    ArchitectLLM,
    CoderLLM,
    DesignerLLM,
    ExecutorRunner,
    VerifierGetter,
    make_architect_node,
    make_coder_node,
    make_designer_node,
    make_executor_node,
)
from .router import route_after_executor
from .schema import FailureMode, IterationRecord
from .state import V1State
from .verifiers import get_verifier

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


_TARGET_NODE_MAP = {
    "architect": "architect",
    "designer": "designer",
    "coder": "coder",
    "end_success": "end_success",
    "end_budget": "end_budget",
    "end_oscillation": "end_oscillation",
    "end_schema_violation": "end_schema_violation",
}


def _record_iteration(state: V1State) -> V1State:
    """executor 후: IterationContext.iterations append + iteration += 1.

    router 가 이 후 state 를 받아 oscillation count (현재 sig 포함) + iteration
    cap 체크. timestamp 는 ISO-8601 UTC.
    """
    v = state.verification
    sig = v.feedback.blocking_signature if (v and v.feedback) else ""
    failure = v.failure_mode if v else FailureMode.NONE
    record = IterationRecord(
        iter_index=state.iteration,
        node="executor",
        failure_mode=failure,
        blocking_signature=sig,
        timestamp_iso=datetime.now(UTC).isoformat(),
    )
    new_ctx = state.context.append_iteration(record)
    return state.model_copy(
        update={"context": new_ctx, "iteration": state.iteration + 1}
    )


def _finalize_success(state: V1State) -> V1State:
    return state.model_copy(update={"final_status": "success"})


def _finalize_budget(state: V1State) -> V1State:
    return state.model_copy(update={"final_status": "fail_budget_exhausted"})


def _finalize_oscillation(state: V1State) -> V1State:
    return state.model_copy(update={"final_status": "fail_oscillation"})


def _finalize_schema_violation(state: V1State) -> V1State:
    return state.model_copy(update={"final_status": "fail_schema_violation"})


def build_graph(
    *,
    architect_llm: ArchitectLLM | None = None,
    designer_llm: DesignerLLM | None = None,
    coder_llm: CoderLLM | None = None,
    runner: ExecutorRunner | None = None,
    verifier_getter: VerifierGetter = get_verifier,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """v1 graph 빌드. 모든 LLM/runner/verifier 주입 가능 (test mock 지원).

    None 인 dependency 는 production default 사용 (Anthropic LLM, auto-tier
    sandbox, registered verifier). integration test 는 모두 mock 주입.
    """
    builder: StateGraph = StateGraph(V1State)  # type: ignore[type-arg]

    # langgraph add_node 의 NodeInputT generic 이 wrap된 Callable 과 직접 매칭
    # 못 함 — v0 graph.py 와 동일 cast(Any) 우회.
    builder.add_node("architect", cast(Any, make_architect_node(llm=architect_llm)))
    builder.add_node("designer", cast(Any, make_designer_node(llm=designer_llm)))
    builder.add_node("coder", cast(Any, make_coder_node(llm=coder_llm)))
    builder.add_node(
        "executor",
        cast(
            Any,
            make_executor_node(runner=runner, verifier_getter=verifier_getter),
        ),
    )
    builder.add_node("record", cast(Any, _record_iteration))
    builder.add_node("end_success", cast(Any, _finalize_success))
    builder.add_node("end_budget", cast(Any, _finalize_budget))
    builder.add_node("end_oscillation", cast(Any, _finalize_oscillation))
    builder.add_node("end_schema_violation", cast(Any, _finalize_schema_violation))

    builder.set_entry_point("architect")
    builder.add_edge("architect", "designer")
    builder.add_edge("designer", "coder")
    builder.add_edge("coder", "executor")
    builder.add_edge("executor", "record")

    builder.add_conditional_edges(
        "record", route_after_executor, cast(Any, _TARGET_NODE_MAP)
    )

    for terminal in (
        "end_success",
        "end_budget",
        "end_oscillation",
        "end_schema_violation",
    ):
        builder.add_edge(terminal, END)

    return builder.compile()
