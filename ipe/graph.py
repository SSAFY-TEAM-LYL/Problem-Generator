"""LangGraph 빌더 — P7 conditional routing + decision/halt + iteration_history.

스펙: ARCHITECTURE.md §3.4, IMPLEMENTATION_ROADMAP §1 P7.1/P7.2

흐름::

    START → architect → coder → executor → decision → {architect, coder, auditor, generator, END}
                                              ↑
                                  auditor → ──┤
                                  generator → ┘

`decision` 노드:
- cost guard: ``sum(llm_calls.cost_usd) > max_cost_usd`` → ``cost_exceeded``
- final_status="success" → END (executor가 set한 그대로)
- max_iter: ``iteration_count >= max_iter`` → ``max_iterations``
- budget: ``node_retry_budget[failed] <= 0`` → ``budget_exhausted``
- 그 외 retry: budget 차감 + iteration_history 추가

`route_after_decision` (conditional_edges 함수):
- final_status set → END
- last_failed_node ∈ {architect, coder, auditor, generator} → 그 노드로
- 그 외 → END (안전 종료)

P8 (예정): SqliteSaver checkpointer 주입.
P9 (예정): evaluator 노드 추가 (success 분기).
"""

from __future__ import annotations

import hashlib
from functools import partial
from pathlib import Path
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from ipe.nodes import architect, auditor, coder, evaluator, executor, generator
from ipe.observability import LLMCallTracker
from ipe.sandbox.runner import SandboxedRunner
from ipe.state import IterationRecord, NodeRetryBudget, ProblemState

_RETRY_TARGETS = ("architect", "coder", "auditor", "generator")


def _error_signature(feedback: str) -> str:
    """feedback_message → SHA-1 hash 앞 12자.

    동일 시그니처가 iteration_history에 누적되면 oscillation 신호로
    `_build_history_section`(P7.3)이 강한 경고를 user prompt에 삽입한다.
    """
    if not feedback:
        return ""
    return hashlib.sha1(feedback.encode("utf-8")).hexdigest()[:12]


def _detect_architect_oscillation(state: ProblemState, current_signature: str) -> bool:
    """R-osc-break: architect가 같은 signature로 2회+ 실패했는지 감지.

    prompt-only W4 경고(`_build_history_section`)는 LLM이 무시 가능 → BFS variance
    사례에서 architect가 같은 패턴으로 반복 retry하다 budget 소진. 이 함수가 True
    리턴 시 `_decision`이 ``last_failed_node``를 ``architect → coder``로 swap하여
    결정적으로 oscillation 차단.

    조건 (전부 만족):
    - 현 cycle의 ``last_failed_node == "architect"``
    - ``current_signature`` 비어있지 않음
    - ``iteration_history``에 ``node="architect"`` + 동일 signature 1회+ 존재
      (이번 포함 = 2회+)
    """
    if state.get("last_failed_node") != "architect":
        return False
    if not current_signature:
        return False
    history = state.get("iteration_history") or []
    prior = sum(
        1
        for r in history
        if r.get("node") == "architect" and r.get("error_signature") == current_signature
    )
    return prior >= 1


def _decision(state: ProblemState) -> ProblemState:
    """Halt 가드 + iteration_history 갱신 + budget 차감.

    우선순위 (앞 순서가 후 순서를 short-circuit):

    1. **cost guard** — 누적 cost > ``max_cost_usd`` → ``cost_exceeded``
    2. **success** — executor가 set한 ``final_status="success"`` 보존
    3. **max_iter** — ``iteration_count >= max_iter`` → ``max_iterations``
    4. **budget exhausted** — ``node_retry_budget[failed] <= 0`` → ``budget_exhausted``
    5. **retry** — ``last_failed_node`` 설정 시 budget 차감 + history 추가
    """
    # 1. cost guard
    llm_calls = state.get("llm_calls") or []
    total_cost = sum(float(c.get("cost_usd", 0.0)) for c in llm_calls)
    max_cost = state.get("max_cost_usd")
    if max_cost is not None and total_cost > max_cost:
        return {
            **state,
            "final_status": "cost_exceeded",
            "feedback_message": (
                f"cost guard: ${total_cost:.4f} > max_cost_usd ${max_cost:.4f}"
            ),
        }

    # 2. success — executor가 이미 결정
    if state.get("final_status") == "success":
        return state

    iter_count = state.get("iteration_count", 0)
    max_iter = state.get("max_iter") or 0

    # 3. max_iter — iteration safety net
    if max_iter > 0 and iter_count >= max_iter:
        return {
            **state,
            "final_status": "max_iterations",
            "feedback_message": (
                f"max_iter reached: iteration_count={iter_count} >= max_iter={max_iter}"
            ),
        }

    # 4. R-osc-break: architect oscillation 감지 → coder 강제 라우팅 swap
    failed = state.get("last_failed_node")
    feedback = state.get("feedback_message") or ""
    current_sig = _error_signature(feedback)
    osc_break = _detect_architect_oscillation(state, current_sig)
    # 원인 노드(architect)는 history에 그대로 기록, routing/budget만 coder로 swap
    origin_node = failed
    if osc_break:
        failed = "coder"

    # 5. budget exhausted — NodeRetryBudget(TypedDict)을 dict[str,int]로 narrow
    nb_src: dict[str, Any] = dict(state.get("node_retry_budget") or {})
    budget: dict[str, int] = {k: int(v) for k, v in nb_src.items()}
    if failed in _RETRY_TARGETS:
        remaining = budget.get(str(failed), 0)
        if remaining <= 0:
            return {
                **state,
                "final_status": "budget_exhausted",
                "feedback_message": (
                    f"{failed} retry budget exhausted (was {remaining})"
                ),
            }
        # 6. retry — budget 차감
        budget[str(failed)] = remaining - 1

    # iteration_history 추가 (failed가 set된 경우에만)
    history: list[IterationRecord] = list(state.get("iteration_history") or [])
    if origin_node:
        record: IterationRecord = {
            "iter_index": iter_count,
            "node": str(origin_node),
            "action": "oscillation_break" if osc_break else "retry",
            "error_signature": current_sig,
            "feedback": feedback,
        }
        history.append(record)

    return {
        **state,
        "node_retry_budget": cast(NodeRetryBudget, budget),
        "iteration_history": history,
        "last_failed_node": failed,
    }


def _route_after_decision(state: ProblemState) -> str:
    """conditional_edges 분기 — next node name or END.

    - final_status="success" → ``evaluator`` (P9.3, 난이도 측정 후 END)
    - final_status ∈ {max_iterations, budget_exhausted, cost_exceeded} → END
    - last_failed_node ∈ {architect, coder, auditor, generator} → 그 노드 재실행
    - 그 외(이상 상태) → END (안전 종료)
    """
    if state.get("final_status") == "success":
        return "evaluator"
    if state.get("final_status"):
        return END
    failed = state.get("last_failed_node")
    if failed in _RETRY_TARGETS:
        return str(failed)
    return END


def build_graph(
    *,
    tracker: LLMCallTracker,
    runner: SandboxedRunner,
    workdir_root: Path | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> Any:
    """3-Phase 검증 + conditional routing 그래프.

    노드 5개 (architect/coder/auditor/generator/executor) + decision 1개.
    의존성 (LLMCallTracker, SandboxedRunner)은 ``functools.partial``로 keyword-only
    bind. LangGraph는 노드를 ``(state) -> state``로 호출하므로 시그니처가 맞는다.

    P8: ``checkpointer`` (예: ``SqliteSaver``)가 주어지면 노드 단위 영속화 +
    ``--resume`` 가능. None이면 in-memory만.
    """
    g = StateGraph(ProblemState)
    g.add_node("architect", partial(architect.run, tracker=tracker))
    g.add_node("coder", partial(coder.run, tracker=tracker))
    g.add_node("auditor", partial(auditor.run, tracker=tracker))
    g.add_node(
        "generator",
        partial(generator.run, tracker=tracker, runner=runner, workdir_root=workdir_root),
    )
    g.add_node(
        "executor",
        partial(executor.run, runner=runner, workdir_root=workdir_root),
    )
    g.add_node("decision", _decision)
    g.add_node("evaluator", partial(evaluator.run, tracker=tracker))

    # 직선 entry — first iteration: architect → coder → executor → decision
    g.add_edge(START, "architect")
    g.add_edge("architect", "coder")
    g.add_edge("coder", "executor")
    # auditor/generator는 decision으로부터만 진입 → executor로 다시
    g.add_edge("auditor", "executor")
    g.add_edge("generator", "executor")
    g.add_edge("executor", "decision")
    # P9: success → evaluator → END (난이도 측정)
    g.add_edge("evaluator", END)

    # decision의 conditional 분기
    g.add_conditional_edges(
        "decision",
        _route_after_decision,
        {
            "architect": "architect",
            "coder": "coder",
            "auditor": "auditor",
            "generator": "generator",
            "evaluator": "evaluator",
            END: END,
        },
    )
    return g.compile(checkpointer=checkpointer) if checkpointer else g.compile()
