"""IterationContext — v1 graph state 의 stateful learning layer.

기존 (v0): ``state["iteration_history"]: list[IterationRecord]`` — prose feedback.
재실행 시 휘발 (skill amnesia).

v1 핵심: structured iterations + 같은 algorithm 의 prior runs 에서
``learned_invariants`` 를 retrieve 해서 cold-start 회피 (D안 H3).

Phase 1 단계: in-memory 누적만. Phase 3 (skill library M5) 에서 catalog 영속화.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .algorithm_design import Invariant
from .solution_attempt import Lesson
from .verification_result import FailureMode


class IterationRecord(BaseModel):
    """한 iteration 의 요약 (v0 ``IterationRecord`` 의 typed 후속)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    iter_index: int = Field(..., ge=0)
    node: str = Field(..., min_length=1)
    failure_mode: FailureMode = FailureMode.NONE
    blocking_signature: str = ""
    timestamp_iso: str = Field(..., min_length=1)


class FailedStrategy(BaseModel):
    """같은 algorithm 의 prior 시도에서 실패가 입증된 접근. 재실행 시 회피."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    signature: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    failure_mode: FailureMode
    occurred_at_iter: int = Field(..., ge=0)


class IterationContext(BaseModel):
    """v1 graph 의 stateful learning layer.

    노드는 read-only 로 접근. 새 record 추가 시 ``append_*`` 메서드 통해
    immutable 갱신 (frozen=True 보존).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(..., min_length=1)
    target_algorithm: str = Field(..., min_length=1)
    iterations: list[IterationRecord] = Field(default_factory=list)
    accumulated_lessons: list[Lesson] = Field(
        default_factory=list, description="signature 기준 dedup"
    )
    failed_strategies: list[FailedStrategy] = Field(default_factory=list)
    learned_invariants: list[Invariant] = Field(
        default_factory=list,
        description="prior runs 에서 가져온 algorithm 별 invariants",
    )

    def append_iteration(self, record: IterationRecord) -> IterationContext:
        """Immutable append. 새 ``IterationContext`` 반환."""
        return self.model_copy(update={"iterations": [*self.iterations, record]})

    def append_lesson(self, lesson: Lesson) -> IterationContext:
        """Lesson signature dedup. 이미 있으면 self 반환."""
        if any(existing.signature == lesson.signature for existing in self.accumulated_lessons):
            return self
        return self.model_copy(
            update={"accumulated_lessons": [*self.accumulated_lessons, lesson]}
        )

    def append_failed_strategy(self, strategy: FailedStrategy) -> IterationContext:
        """Failed strategy signature dedup. 이미 있으면 self 반환."""
        if any(
            existing.signature == strategy.signature
            for existing in self.failed_strategies
        ):
            return self
        return self.model_copy(
            update={"failed_strategies": [*self.failed_strategies, strategy]}
        )
