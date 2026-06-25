"""V2 graph state — B2B blueprint-first 파이프라인 (Phase 3 M3+).

canonical 의 ``V1State`` 와 분리된 fresh state. 검증 해자의 typed 계약(``ipe.v1.
schema``)은 재사용하되, blueprint-first 흐름에 맞는 필드를 새로 구성한다:

  seed → strategy(시드) → blueprint(FREEZE) → spec(파생) → candidates(synth) →
  reconciliation → verification → narrative(late) → faithfulness

모든 transition 은 ``model_copy(update=...)`` immutable 갱신. 병렬 synthesis 노드는
``candidates`` reducer 채널에 partial dict append (멱등 dedup-concat — M2 step4 의
발견 재사용: reconciler 이후 full-state 재emit 에도 중복 누적 없음).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ipe.v1.schema import (
    AlgorithmDesign,
    GeneratorContract,
    IRValidationReport,
    IterationContext,
    Narrative,
    NarrativeFaithfulnessReport,
    ProblemBlueprint,
    ProblemSpec,
    QAReport,
    QAReview,
    ReconciliationResult,
    ResolvedEdgeCase,
    SolutionAttempt,
    SolutionCandidate,
    StrategySeed,
    TargetAlgorithm,
    TestSuite,
    VerificationResult,
)

from .config import MAX_ITERATIONS_DEFAULT

V2FinalStatus = Literal[
    "success",
    "fail_validation",  # IR validator Tier A 실패 (ill-posed IR, back-route 예산 소진)
    "fail_synthesis_rejected",  # golden/brute 합의 실패
    "fail_verification",  # canonical 이 검증 실패
    "fail_faithfulness",  # narrative round-trip 왜곡 (다른 문제 기술)
    "fail_qa",  # QA 리뷰어 게이트 실패 (M5 — 모호성/공정성/유출/난이도)
    "fail_budget_exhausted",
]

# config 단일 소스를 state 의 기존 공개 이름으로 재노출 (main_v2 가 여기서 import).
DEFAULT_MAX_ITERATIONS = MAX_ITERATIONS_DEFAULT


def _merge_candidates(
    left: list[SolutionCandidate], right: list[SolutionCandidate]
) -> list[SolutionCandidate]:
    """``candidates`` reducer — fan-out 누적 + full-state 재emit 멱등 (dedup-concat).

    M2 step4 발견과 동일: 병렬 fan-out 은 distinct 후보 append, 하류 노드의
    full-state 재emit 은 동일 후보 1회만 유지 → candidates 가 fan-out 폭에 고정.
    """
    merged = list(left)
    merged.extend(c for c in right if c not in merged)
    return merged


def _merge_qa_reviews(
    left: list[QAReview], right: list[QAReview]
) -> list[QAReview]:
    """``qa_reviews`` reducer — 4 병렬 리뷰어(N10a-d) fan-out 멱등 (candidates 동일)."""
    merged = list(left)
    merged.extend(r for r in right if r not in merged)
    return merged


class V2State(BaseModel):
    """B2B blueprint-first 그래프가 운반하는 typed state.

    ``seed_algorithm`` = 은닉할 코어(입력 hint). Strategist 가 이를 ``strategy``
    시드로 발산 → Formalizer 가 ``blueprint`` 로 freeze, narrative 는 last 렌더.
    solver/executor 는 blueprint 파생 ``spec`` 을 입력으로 받는다 (해자 재사용).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Meta
    run_id: str = Field(..., min_length=1)
    seed_algorithm: TargetAlgorithm = Field(
        ..., description="은닉할 코어 알고리즘 (Strategist 입력 hint)"
    )
    iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=DEFAULT_MAX_ITERATIONS, gt=0)
    validator_routebacks: int = Field(
        default=0, ge=0, description="validator fail→formalizer back-route 소비 횟수"
    )
    max_validator_routebacks: int = Field(
        default=1, ge=0, description="validator back-route 예산 (0=단발 게이트)"
    )

    # blueprint-first 산출물 (단계별 lazily populate)
    strategy: StrategySeed | None = None  # Strategist 시드 (은닉 코어+합성+도메인)
    blueprint: ProblemBlueprint | None = None  # Formalizer FREEZE
    validation: IRValidationReport | None = None  # IR validator Tier A (RFC §6)
    generator_contract: GeneratorContract | None = None  # M4 입력 생성기 계약 (LLM 저작)
    spec: ProblemSpec | None = None  # blueprint → solver/executor 입력 순수 투영
    design: AlgorithmDesign | None = None  # spec → solver invariants (M2 designer 재사용)
    candidates: Annotated[list[SolutionCandidate], _merge_candidates] = Field(
        default_factory=list, description="golden×K + brute 병렬 후보 (reducer)"
    )
    reconciliation: ReconciliationResult | None = None
    attempt: SolutionAttempt | None = None  # reconciled canonical → executor 입력
    resolved_edges: tuple[ResolvedEdgeCase, ...] = Field(
        default=(),
        description=(
            "Phase 5a — IR 파생 퇴화 엣지 케이스. v2 reconciler 가 differential 에 더해 "
            "diff·기록(pending), edge_filler 가 canonical golden 으로 expected 채움 "
            "(엣지 의미 golden-defined, RFC §3.3)"
        ),
    )
    verification: VerificationResult | None = None
    narrative: Narrative | None = None  # late 렌더 (은닉)
    faithfulness: NarrativeFaithfulnessReport | None = None
    test_suite: TestSuite | None = None  # M4 풀 채점셋 (입력 생성 → assembler 가 expected)
    qa_reviews: Annotated[list[QAReview], _merge_qa_reviews] = Field(
        default_factory=list, description="M5 QA 리뷰어 4종 병렬 산출 (reducer)"
    )
    qa_report: QAReport | None = None  # M5 aggregator 집계 (출하 게이트 근거)
    qa_routebacks: int = Field(
        default=0, ge=0, description="B back-route 소비 횟수 (QA fail→재진입)"
    )
    max_qa_routebacks: int = Field(
        default=1, ge=0, description="B back-route 예산 (0=단발 게이트)"
    )

    # Stateful learning (해자 재사용)
    context: IterationContext

    # Control
    final_status: V2FinalStatus | None = None

    @property
    def target_algorithm(self) -> TargetAlgorithm:
        """verifier dispatch 용 실 알고리즘 (M2 노드 재사용 어댑터).

        v1 executor/designer 는 ``state.target_algorithm`` 으로 verifier 를 dispatch
        한다. v2 는 ``seed_algorithm``(은닉 hint)만 top-level 로 갖고 실 알고리즘은
        ``spec.target_algorithm``(= blueprint.reduction_core, spec_bridge 가 carry-over)
        에 있다. spec 미생성(모델링 단계)이면 seed 로 fallback. computed property 라
        langgraph 채널이 아니다 (직렬화/reducer 무관).
        """
        return (
            self.spec.target_algorithm
            if self.spec is not None
            else self.seed_algorithm
        )


def initial_v2_state(
    run_id: str,
    seed_algorithm: TargetAlgorithm,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    max_qa_routebacks: int = 1,
    max_validator_routebacks: int = 1,
) -> V2State:
    """Factory — 최소 입력으로 V2State 시작 상태 생성.

    ``context`` 는 같은 run_id / seed_algorithm 으로 초기화 (해자 IterationContext).
    ``max_qa_routebacks`` 는 QA fail 시 back-route(B) 예산 (0=단발 게이트).
    ``max_validator_routebacks`` 는 IR validator fail 시 formalizer 재진입 예산.
    """
    return V2State(
        run_id=run_id,
        seed_algorithm=seed_algorithm,
        max_iterations=max_iterations,
        max_qa_routebacks=max_qa_routebacks,
        max_validator_routebacks=max_validator_routebacks,
        context=IterationContext(
            run_id=run_id,
            target_algorithm=seed_algorithm,
        ),
    )
