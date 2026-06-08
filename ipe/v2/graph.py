"""v2 LangGraph builder — 은닉 모델링 + (옵션) synthesis/verification (Phase 3 M3/통합).

``with_synthesis=False`` (기본, 모델링 layer 만)::

    START → strategist → formalizer → narrative → faithfulness → route ─┬─ end_success
              (시드)      (FREEZE)     (은닉 렌더)   (round-trip)         │   (success)
                                          ▲                              ├─ regen → narrative
                                          └──────────────────────────────┘  (faithful=False)
                                       route(budget 소진) ── end_faithfulness

``with_synthesis=True`` (M2 full-mode 재사용으로 '문제+검증된 정답' 생성)::

    faithfulness ─(faithful)→ spec_bridge → designer → dispatch ─┬→ golden_0..K ─┐
                                                                 └→ brute ───────┴→ reconciler
      reconciler ─(채택)→ synth_bridge → executor → route ─(pass)→ end_success
                                                          └(fail)→ end_verification
      reconciler ─(reject)→ end_synthesis_rejected

핵심 의도:
- 모델링 4 노드(strategist/formalizer/narrative/faithfulness) + faithful=False→narrative
  재생성(``max_iterations`` 바운드). 왜곡만 reject, 은닉은 통과.
- synthesis 는 **v1 M2 노드 재사용**(designer/synthesis_coder/reconciler/synth_bridge/
  executor) — V2State 가 design/attempt 채널 + target_algorithm property 로 적응(step2a).
  approach (a): spec_bridge LLM 이 sample 저작, golden↔brute differential + symbolic
  verifier 가 검증. fix-loop 없음(단발, M3+ 반복정제 별개).
- ``with_synthesis=False`` 는 모델링 layer 만 — 기존 test/CLI backward compat.

recursion 주의: 모델링 루프 1회=3 step + synthesis ~6 step. ``max_iterations`` 크면
invoke ``config={"recursion_limit": N}`` 상향.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from langgraph.graph import END, StateGraph

from ipe.sandbox.selector import pick_runner
from ipe.v1.nodes import (
    make_designer_node,
    make_executor_node,
    make_reconciler_node,
    make_synth_bridge_node,
    make_synthesis_coder_node,
)
from ipe.v1.router import route_after_full_executor, route_after_reconcile
from ipe.v1.verifiers import get_verifier

from .nodes import (
    FaithfulnessLLM,
    FormalizerLLM,
    NarrativeLLM,
    SpecBridgeLLM,
    StrategistLLM,
    make_faithfulness_node,
    make_formalizer_node,
    make_narrative_node,
    make_spec_bridge_node,
    make_strategist_node,
)
from .router import route_after_faithfulness
from .state import V2FinalStatus, V2State

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from langgraph.graph.state import CompiledStateGraph

    from ipe.v1.nodes import CoderLLM, DesignerLLM, ExecutorRunner, VerifierGetter


def _bump_iteration(state: V2State) -> V2State:
    """regen 노드 — faithfulness 실패 후 재시도 카운터 증가 (narrative 재생성 전)."""
    return state.model_copy(update={"iteration": state.iteration + 1})


def _make_finalizer(status: V2FinalStatus) -> Callable[[V2State], V2State]:
    """terminal 노드 팩토리 — final_status set 후 END."""

    def node(state: V2State) -> V2State:
        return state.model_copy(update={"final_status": status})

    return node


def _fanout_dispatch(_state: V2State) -> dict[str, Any]:
    """synthesis fan-out trigger — state 무변경 (빈 partial dict)."""
    return {}


def _v2_full_node(v1_node: Any) -> Callable[[V2State], V2State]:
    """full-state 반환 v1 노드(designer/executor, ``-> V1State`` 주석)를 ``-> V2State``
    로 감싼다.

    langgraph 는 노드 return 주석으로 output-schema 를 추론한다. v1 노드의 ``V1State``
    주석을 그대로 쓰면 V1State.candidates(``operator.add`` reducer)가 V2State.candidates
    (``_merge_candidates`` reducer)와 채널 타입 충돌 → compile 실패. 이 래퍼가 return
    주석을 V2State 로 바꿔 그 추론을 막는다 (런타임은 이미 V2State 반환 — 무변화).
    """

    def node(state: V2State) -> V2State:
        return cast(V2State, v1_node(state))

    return node


def _v2_partial_node(v1_node: Any) -> Callable[[V2State], dict[str, Any]]:
    """partial-dict 반환 v1 노드(synthesis_coder/reconciler/synth_bridge)를 ``-> dict[
    str, Any]`` 로 감싼다.

    v1 노드 return 주석(예: ``dict[str, list[SolutionCandidate]]``)을 langgraph 가
    읽으면 candidates 등 typed write-channel 을 추론 → V2State 의 reducer 채널과 충돌.
    ``dict[str, Any]`` 주석은 그 추론을 막고 state-schema 채널(reducer 포함)에 그대로
    write 한다 (런타임 dict 무변화 — candidates accumulation/dedup 정상).
    """

    def node(state: V2State) -> dict[str, Any]:
        return cast("dict[str, Any]", v1_node(state))

    return node


def _v2_router(v1_router: Any) -> Callable[[V2State], str]:
    """v1 router(`route_after_reconcile`/`route_after_full_executor`, ``(V1State)`` 주석)
    를 ``(V2State)`` 입력 주석으로 감싼다.

    langgraph 는 conditional-edge path 함수의 입력 주석으로도 schema 를 추론한다. v1
    router 의 V1State 주석을 그대로 쓰면 V1State.candidates(``operator.add``)가 V2State
    의 ``_merge_candidates`` 채널과 충돌. 이 래퍼가 추론 schema 를 V2State 로 고정한다.
    """

    def route(state: V2State) -> str:
        return cast(str, v1_router(state))

    return route


def build_v2_graph(
    *,
    strategist_llm: StrategistLLM | None = None,
    formalizer_llm: FormalizerLLM | None = None,
    narrative_llm: NarrativeLLM | None = None,
    faithfulness_llm: FaithfulnessLLM | None = None,
    hidden: bool = True,
    with_synthesis: bool = False,
    spec_bridge_llm: SpecBridgeLLM | None = None,
    designer_llm: DesignerLLM | None = None,
    golden_llms: Sequence[CoderLLM] | None = None,
    brute_llm: CoderLLM | None = None,
    golden_origins: Sequence[str] | None = None,
    brute_origin: str = "naive",
    runner: ExecutorRunner | None = None,
    verifier_getter: VerifierGetter = get_verifier,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """v2 그래프 빌드. None dependency 는 production default(Anthropic/sandbox/verifier).

    ``hidden`` = narrative 렌더 모드. ``with_synthesis=True`` 면 faithful 통과 후
    spec_bridge→synthesis(M2 재사용)→verification 까지 — ``golden_llms``(>=1) +
    ``brute_llm`` 필수. test 는 모든 LLM mock 주입.
    """
    builder: StateGraph = StateGraph(V2State)  # type: ignore[type-arg]

    # ---- modeling nodes (always) ----
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
    builder.add_edge("regen", "narrative")  # 재생성 루프
    builder.add_edge("end_success", END)
    builder.add_edge("end_faithfulness", END)

    # faithful 통과 시: 모델링-only 면 end_success, synthesis 면 spec_bridge 로 진행
    faithful_target = "spec_bridge" if with_synthesis else "end_success"
    builder.add_conditional_edges(
        "faithfulness",
        route_after_faithfulness,
        cast(
            Any,
            {
                "end_success": faithful_target,
                "regen": "regen",
                "end_faithfulness": "end_faithfulness",
            },
        ),
    )

    if with_synthesis:
        _wire_synthesis(
            builder,
            spec_bridge_llm=spec_bridge_llm,
            designer_llm=designer_llm,
            golden_llms=golden_llms,
            brute_llm=brute_llm,
            golden_origins=golden_origins,
            brute_origin=brute_origin,
            runner=runner,
            verifier_getter=verifier_getter,
        )

    return builder.compile()


def _wire_synthesis(
    builder: Any,
    *,
    spec_bridge_llm: SpecBridgeLLM | None,
    designer_llm: DesignerLLM | None,
    golden_llms: Sequence[CoderLLM] | None,
    brute_llm: CoderLLM | None,
    golden_origins: Sequence[str] | None,
    brute_origin: str,
    runner: ExecutorRunner | None,
    verifier_getter: VerifierGetter,
) -> None:
    """synthesis 서브그래프 — spec_bridge→designer→fan-out→reconcile→bridge→executor.

    v1 M2 노드를 cast(Any) duck-typing 으로 재사용(step2a 가 V2State 적응으로 검증).
    """
    if not golden_llms or brute_llm is None:
        msg = "with_synthesis=True 는 golden_llms(>=1) + brute_llm 필수"
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

    builder.add_node("spec_bridge", cast(Any, make_spec_bridge_node(spec_bridge_llm)))
    builder.add_node(
        "designer", cast(Any, _v2_full_node(make_designer_node(designer_llm)))
    )
    builder.add_node("dispatch", cast(Any, _fanout_dispatch))
    golden_names: list[str] = []
    for i, (llm, origin) in enumerate(zip(golden_llms, origins, strict=True)):
        name = f"golden_{i}"
        golden_names.append(name)
        builder.add_node(
            name,
            cast(
                Any,
                _v2_partial_node(
                    make_synthesis_coder_node(
                        llm, role="golden", origin=origin, fanout_index=i
                    )
                ),
            ),
        )
    builder.add_node(
        "brute",
        cast(
            Any,
            _v2_partial_node(
                make_synthesis_coder_node(
                    brute_llm, role="brute", origin=brute_origin, fanout_index=0
                )
            ),
        ),
    )
    builder.add_node(
        "reconciler", cast(Any, _v2_partial_node(make_reconciler_node(synth_runner)))
    )
    builder.add_node(
        "synth_bridge", cast(Any, _v2_partial_node(make_synth_bridge_node()))
    )
    builder.add_node(
        "executor",
        cast(
            Any,
            _v2_full_node(
                make_executor_node(runner=runner, verifier_getter=verifier_getter)
            ),
        ),
    )
    builder.add_node(
        "end_verification", cast(Any, _make_finalizer("fail_verification"))
    )
    builder.add_node(
        "end_synthesis_rejected",
        cast(Any, _make_finalizer("fail_synthesis_rejected")),
    )

    builder.add_edge("spec_bridge", "designer")
    builder.add_edge("designer", "dispatch")
    for name in (*golden_names, "brute"):
        builder.add_edge("dispatch", name)  # fan-out (parallel superstep)
        builder.add_edge(name, "reconciler")  # fan-in (join once)
    builder.add_conditional_edges(
        "reconciler",
        _v2_router(route_after_reconcile),
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
        "executor",
        _v2_router(route_after_full_executor),
        cast(
            Any,
            {
                "end_success": "end_success",
                "end_verification_fail": "end_verification",
            },
        ),
    )
    builder.add_edge("end_verification", END)
    builder.add_edge("end_synthesis_rejected", END)
