"""v1 LangGraph builder (D안 PR-A3 + Phase 3 M2 step4 full mode).

compat flag ``mode`` 로 두 토폴로지 선택 (RFC §10)::

    mode="canonical" (기본):
      START → architect → designer → coder → executor → record → router →
                                                          ├── architect
                                                          ├── designer
                                                          ├── coder
                                                          ├── end_success
                                                          ├── end_budget
                                                          ├── end_oscillation
                                                          └── end_schema_violation → END

    mode="full" (병렬 synthesis):
      START → architect → designer → dispatch ─┬→ golden_0..K ─┐
                                               └→ brute ───────┴→ reconciler
        reconciler →(채택) synth_bridge → executor → record →
                       (pass) end_success / (fail) end_verification_fail → END
        reconciler →(reject) end_synthesis_rejected → END

핵심 의도:
- canonical = 영구 B2C 토픽드릴 + 91.2% anchor 경로. 토폴로지 **불변**.
- full = B2B 병렬 synthesis (golden×K + brute → differential reconcile → single-shot
  검증). fix-loop 없음 (반복 정제는 M3+). RFC full anchor = 단발 출하가능률.
- ``executor``/``record``/finalize 는 두 mode 공용. candidates reducer 가 멱등
  (``_merge_candidates``) 이라 full mode 에서 이 노드들의 full-state 재emit 에도
  candidates 가 중복되지 않는다 (step3 발견 대응 — production 노드 무수정).
- ``route_*`` (router.py) 가 enum/threshold 기반 결정론적 dispatch (D안 H1).

dependency injection: graph build 시 모든 LLM/runner/verifier_getter 주입 가능 —
integration test 가 mock 으로 결정론 시나리오 재현. full mode 는 ``golden_llms`` +
``brute_llm`` 추가 주입.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from langgraph.graph import END, StateGraph

from ipe.sandbox.selector import pick_runner

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
    make_reconciler_node,
    make_synth_bridge_node,
    make_synthesis_coder_node,
)
from .router import (
    route_after_executor,
    route_after_full_executor,
    route_after_reconcile,
)
from .schema import FailureMode, IterationRecord
from .state import FinalStatus, V1State
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


def _make_finalizer(status: FinalStatus) -> Callable[[V1State], V1State]:
    """terminal 노드 팩토리 — final_status set 후 END (canonical/full 공용)."""

    def node(state: V1State) -> V1State:
        return state.model_copy(update={"final_status": status})

    return node


def _fanout_dispatch(_state: V1State) -> dict[str, Any]:
    """full mode fan-out trigger — state 무변경 (빈 partial dict)."""
    return {}


def build_graph(
    *,
    mode: Literal["canonical", "full"] = "canonical",
    architect_llm: ArchitectLLM | None = None,
    designer_llm: DesignerLLM | None = None,
    coder_llm: CoderLLM | None = None,
    runner: ExecutorRunner | None = None,
    verifier_getter: VerifierGetter = get_verifier,
    golden_llms: Sequence[CoderLLM] | None = None,
    brute_llm: CoderLLM | None = None,
    golden_origins: Sequence[str] | None = None,
    brute_origin: str = "naive",
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """v1 graph 빌드 — compat flag ``mode`` 로 canonical/full 토폴로지 선택 (RFC §10).

    None 인 dependency 는 production default 사용 (Anthropic LLM, auto-tier sandbox,
    registered verifier). integration test 는 모두 mock 주입. ``mode="full"`` 은
    ``golden_llms`` (>=1) + ``brute_llm`` 추가 필수.
    """
    builder: StateGraph = StateGraph(V1State)  # type: ignore[type-arg]

    # ---- shared nodes (canonical/full 공용) ----
    builder.add_node("architect", cast(Any, make_architect_node(llm=architect_llm)))
    builder.add_node("designer", cast(Any, make_designer_node(llm=designer_llm)))
    builder.add_node(
        "executor",
        cast(Any, make_executor_node(runner=runner, verifier_getter=verifier_getter)),
    )
    builder.add_node("record", cast(Any, _record_iteration))
    builder.add_node("end_success", cast(Any, _make_finalizer("success")))

    builder.set_entry_point("architect")
    builder.add_edge("architect", "designer")
    builder.add_edge("executor", "record")
    builder.add_edge("end_success", END)

    if mode == "canonical":
        _wire_canonical(builder, coder_llm=coder_llm)
    else:
        _wire_full(
            builder,
            golden_llms=golden_llms,
            brute_llm=brute_llm,
            runner=runner,
            golden_origins=golden_origins,
            brute_origin=brute_origin,
        )

    return builder.compile()


def _wire_canonical(builder: Any, *, coder_llm: CoderLLM | None) -> None:
    """canonical(linear) 토폴로지 — 기존 D안 PR-A3 경로 그대로 (anchor 불변)."""
    builder.add_node("coder", cast(Any, make_coder_node(llm=coder_llm)))
    builder.add_node("end_budget", cast(Any, _make_finalizer("fail_budget_exhausted")))
    builder.add_node("end_oscillation", cast(Any, _make_finalizer("fail_oscillation")))
    builder.add_node(
        "end_schema_violation", cast(Any, _make_finalizer("fail_schema_violation"))
    )

    builder.add_edge("designer", "coder")
    builder.add_edge("coder", "executor")
    builder.add_conditional_edges(
        "record", route_after_executor, cast(Any, _TARGET_NODE_MAP)
    )
    for terminal in ("end_budget", "end_oscillation", "end_schema_violation"):
        builder.add_edge(terminal, END)


def _wire_full(
    builder: Any,
    *,
    golden_llms: Sequence[CoderLLM] | None,
    brute_llm: CoderLLM | None,
    runner: ExecutorRunner | None,
    golden_origins: Sequence[str] | None,
    brute_origin: str,
) -> None:
    """full(병렬 synthesis) 토폴로지 — fan-out → reconcile → bridge → 단발 검증."""
    if not golden_llms or brute_llm is None:
        msg = "mode='full' 은 golden_llms(>=1) + brute_llm 필수"
        raise ValueError(msg)
    origins = (
        list(golden_origins)
        if golden_origins is not None
        else [f"golden-{i}" for i in range(len(golden_llms))]
    )
    if len(origins) != len(golden_llms):
        msg = f"golden_origins 길이({len(origins)}) != golden_llms({len(golden_llms)})"
        raise ValueError(msg)
    synth_runner: Any = runner if runner is not None else pick_runner()

    builder.add_node("dispatch", cast(Any, _fanout_dispatch))
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
    builder.add_node("reconciler", cast(Any, make_reconciler_node(synth_runner)))
    builder.add_node("synth_bridge", cast(Any, make_synth_bridge_node()))
    builder.add_node(
        "end_synthesis_rejected",
        cast(Any, _make_finalizer("fail_synthesis_rejected")),
    )
    builder.add_node(
        "end_verification_fail", cast(Any, _make_finalizer("fail_verification"))
    )

    builder.add_edge("designer", "dispatch")
    for name in (*golden_names, "brute"):
        builder.add_edge("dispatch", name)  # fan-out (parallel superstep)
        builder.add_edge(name, "reconciler")  # fan-in (join once)
    builder.add_conditional_edges(
        "reconciler",
        route_after_reconcile,
        cast(
            Any,
            {
                "synth_bridge": "synth_bridge",
                "end_synthesis_rejected": "end_synthesis_rejected",
            },
        ),
    )
    builder.add_edge("synth_bridge", "executor")
    builder.add_conditional_edges(
        "record",
        route_after_full_executor,
        cast(
            Any,
            {
                "end_success": "end_success",
                "end_verification_fail": "end_verification_fail",
            },
        ),
    )
    for terminal in ("end_synthesis_rejected", "end_verification_fail"):
        builder.add_edge(terminal, END)
