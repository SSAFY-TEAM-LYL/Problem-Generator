"""V1 graph state — Pydantic BaseModel (D안 PR-A3).

LangGraph 0.2+ 가 BaseModel state 지원. 모든 transition 은
``model_copy(update=...)`` 로 immutable 갱신. 노드는 새 ``V1State`` 반환
(또는 LangGraph 가 partial dict merge — graph.py 에서 wrap).

v0 의 ``ProblemState`` TypedDict (mutable + 30+ prose fields) 후속. 모든 노드
출력은 typed Pydantic — 노드 간 통신의 information bottleneck 차단 (D안 H1).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schema import (
    AlgorithmDesign,
    IterationContext,
    ProblemSpec,
    ReconciliationResult,
    SolutionAttempt,
    SolutionCandidate,
    TargetAlgorithm,
    VerificationResult,
)

FinalStatus = Literal[
    "success",
    "fail_budget_exhausted",
    "fail_schema_violation",
    "fail_oscillation",
    "fail_kill_switch",
    # full mode (Phase 3 M2 step4) terminals
    "fail_synthesis_rejected",  # 병렬 synthesis 가 canonical 합의 실패 (reconcile reject)
    "fail_verification",  # synthesis canonical 이 sample/invariant 검증 실패 (single-shot)
]

DEFAULT_MAX_ITERATIONS = 8


def _merge_candidates(
    left: list[SolutionCandidate], right: list[SolutionCandidate]
) -> list[SolutionCandidate]:
    """``candidates`` reducer — fan-out 누적 + full-state 재emit 멱등(중복 흡수).

    병렬 fan-out 노드는 distinct 후보를 append (operator.add 처럼 누적). 단 full
    mode 에서 reconciler 이후 ``model_copy`` 로 full state 를 반환하는 기존 노드
    (executor/record/finalize)가 candidates 를 재emit 하면 단순 concat 은 **중복
    누적** → 동일 후보는 1회만 유지(멱등)하도록 dedup-concat 한다. 덕분에 기존
    production 노드를 무수정 유지하면서도 candidates 가 fan-out 폭으로 고정된다.
    (step3 발견: "reducer 이후 full-state 반환 노드는 candidates 재emit 금지" 대응)
    """
    merged = list(left)
    merged.extend(c for c in right if c not in merged)
    return merged


class V1State(BaseModel):
    """v1 LangGraph 가 운반하는 typed state.

    각 노드는 본 state 를 받아 자신의 typed artifact (spec/design/attempt/
    verification) 를 채운 새 instance 반환. ``context`` 는 iteration 누적 (H3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Meta
    run_id: str = Field(..., min_length=1)
    target_algorithm: TargetAlgorithm
    iteration: int = Field(default=0, ge=0, description="0=architect 첫 진입")
    max_iterations: int = Field(
        default=DEFAULT_MAX_ITERATIONS,
        gt=0,
        description="PR-A1 plan 의 coder budget 6 파생, default 8",
    )

    # Lazily populated by each node
    spec: ProblemSpec | None = None
    design: AlgorithmDesign | None = None
    attempt: SolutionAttempt | None = None
    verification: VerificationResult | None = None

    # Parallel solution synthesis (Phase 3 M2) — fan-out reducer 채널 + fan-in 결과.
    # ``candidates`` 는 golden×K + brute 병렬 노드가 각자 partial dict 로 append →
    # ``_merge_candidates`` 가 누적(dedup-concat, frozen+forbid 호환). canonical mode
    # 에서는 비어 있음 (linear 경로 무영향). full mode (step4) 에서만 채워지며, reducer
    # 가 멱등이라 reconciler 이후 기존 노드의 full-state 재emit 에도 중복되지 않는다.
    candidates: Annotated[list[SolutionCandidate], _merge_candidates] = Field(
        default_factory=list,
        description="병렬 golden×K + brute 후보 누적 (reducer 채널)",
    )
    reconciliation: ReconciliationResult | None = None

    # Stateful learning (D안 H3 — IterationContext)
    context: IterationContext

    # Control
    final_status: FinalStatus | None = None


def initial_state(
    run_id: str,
    target_algorithm: TargetAlgorithm,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> V1State:
    """Factory — minimum required fields 만 받아 V1State 시작 상태 생성.

    ``context`` 는 같은 ``run_id`` / ``target_algorithm`` 으로 초기화.
    """
    return V1State(
        run_id=run_id,
        target_algorithm=target_algorithm,
        max_iterations=max_iterations,
        context=IterationContext(
            run_id=run_id,
            target_algorithm=target_algorithm,
        ),
    )
