"""IterationContext immutable append + dedup 단위 테스트 (D안 PR-A1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import (
    FailedStrategy,
    FailureMode,
    Invariant,
    IterationContext,
    IterationRecord,
    Lesson,
    TargetAlgorithm,
)


def _empty_ctx() -> IterationContext:
    return IterationContext(
        run_id="run-001", target_algorithm=TargetAlgorithm.DIJKSTRA
    )


def _record(idx: int = 0, node: str = "coder") -> IterationRecord:
    return IterationRecord(
        iter_index=idx,
        node=node,
        failure_mode=FailureMode.SAMPLE_MISMATCH,
        blocking_signature=f"sig-{idx}",
        timestamp_iso="2026-05-21T00:00:00Z",
    )


def test_iteration_context_starts_empty() -> None:
    ctx = _empty_ctx()
    assert ctx.iterations == []
    assert ctx.accumulated_lessons == []
    assert ctx.failed_strategies == []
    assert ctx.learned_invariants == []


def test_append_iteration_returns_new_immutable_instance() -> None:
    ctx = _empty_ctx()
    rec = _record(0)
    new_ctx = ctx.append_iteration(rec)
    assert new_ctx is not ctx
    assert ctx.iterations == []  # original unchanged
    assert len(new_ctx.iterations) == 1
    assert new_ctx.iterations[0] == rec


def test_append_lesson_dedups_by_signature() -> None:
    ctx = _empty_ctx()
    lesson_a = Lesson(signature="use-heapq", content="Use heapq.", from_iter=0)
    lesson_b = Lesson(
        signature="use-heapq",
        content="Different content but same signature.",
        from_iter=1,
    )
    ctx1 = ctx.append_lesson(lesson_a)
    ctx2 = ctx1.append_lesson(lesson_b)
    assert len(ctx1.accumulated_lessons) == 1
    assert ctx2 is ctx1
    assert ctx1.accumulated_lessons[0].content == "Use heapq."


def test_append_lesson_keeps_distinct_signatures() -> None:
    ctx = _empty_ctx()
    ctx = ctx.append_lesson(Lesson(signature="a", content="x", from_iter=0))
    ctx = ctx.append_lesson(Lesson(signature="b", content="y", from_iter=1))
    assert len(ctx.accumulated_lessons) == 2


def test_append_failed_strategy_dedups() -> None:
    ctx = _empty_ctx()
    s1 = FailedStrategy(
        signature="naive-dfs",
        description="DFS without memo blows stack",
        failure_mode=FailureMode.SAMPLE_TIMEOUT,
        occurred_at_iter=2,
    )
    s2 = FailedStrategy(
        signature="naive-dfs",
        description="another description",
        failure_mode=FailureMode.SAMPLE_CRASH,
        occurred_at_iter=3,
    )
    ctx1 = ctx.append_failed_strategy(s1)
    ctx2 = ctx1.append_failed_strategy(s2)
    assert len(ctx1.failed_strategies) == 1
    assert ctx2 is ctx1


def test_iteration_context_is_frozen() -> None:
    ctx = _empty_ctx()
    with pytest.raises(ValidationError):
        ctx.run_id = "other"


def test_iteration_record_default_failure_mode_is_none() -> None:
    rec = IterationRecord(
        iter_index=0, node="architect", timestamp_iso="2026-05-21T00:00:00Z"
    )
    assert rec.failure_mode == FailureMode.NONE


def test_learned_invariants_can_be_passed_in() -> None:
    inv = Invariant(kind="non_negative_distance", description="d >= 0")
    ctx = IterationContext(
        run_id="r1",
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        learned_invariants=[inv],
    )
    assert len(ctx.learned_invariants) == 1
    assert ctx.learned_invariants[0].kind == "non_negative_distance"


def test_iteration_context_rejects_unsupported_target_algorithm() -> None:
    with pytest.raises(ValidationError):
        IterationContext.model_validate(
            {"run_id": "r1", "target_algorithm": "bfs"}
        )
