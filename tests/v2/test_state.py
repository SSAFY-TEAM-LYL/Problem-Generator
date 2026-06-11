"""V2State 단위 테스트 (Phase 3 M3 — fresh B2B 공간 scaffold).

initial_v2_state factory + 기본값 + frozen + extra=forbid + candidates reducer 멱등.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import QAReview, SolutionCandidate, TargetAlgorithm
from ipe.v2.state import (
    DEFAULT_MAX_ITERATIONS,
    V2State,
    _merge_candidates,
    _merge_qa_reviews,
    initial_v2_state,
)


def test_initial_v2_state_defaults() -> None:
    s = initial_v2_state("run-v2", TargetAlgorithm.DIJKSTRA)
    assert s.run_id == "run-v2"
    assert s.seed_algorithm is TargetAlgorithm.DIJKSTRA
    assert s.iteration == 0
    assert s.max_iterations == DEFAULT_MAX_ITERATIONS
    # blueprint-first 산출물은 아직 미생성
    assert s.blueprint is None
    assert s.spec is None
    assert s.candidates == []
    assert s.reconciliation is None
    assert s.verification is None
    assert s.narrative is None
    assert s.faithfulness is None
    assert s.final_status is None
    # context 는 해자 재사용 (run_id/seed 로 초기화)
    assert s.context.run_id == "run-v2"
    assert s.context.target_algorithm is TargetAlgorithm.DIJKSTRA


def test_v2_state_is_frozen() -> None:
    s = initial_v2_state("r", TargetAlgorithm.BFS)
    with pytest.raises(ValidationError):
        s.iteration = 5  # type: ignore[misc]


def test_v2_state_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        V2State(  # type: ignore[call-arg]
            run_id="r",
            seed_algorithm=TargetAlgorithm.BFS,
            context=initial_v2_state("r", TargetAlgorithm.BFS).context,
            unexpected="nope",
        )


def test_v2_state_immutable_update_via_model_copy() -> None:
    s = initial_v2_state("r", TargetAlgorithm.BFS)
    s2 = s.model_copy(update={"iteration": 3})
    assert s.iteration == 0  # 원본 불변
    assert s2.iteration == 3


def _cand(origin: str, role: str = "golden", idx: int = 0) -> SolutionCandidate:
    return SolutionCandidate(
        role=role,  # type: ignore[arg-type]
        origin=origin,
        code=f"# {origin}",
        fanout_index=idx,
    )


def test_merge_candidates_accumulates_distinct() -> None:
    a = _cand("opus", idx=0)
    b = _cand("sonnet", idx=1)
    assert _merge_candidates([a], [b]) == [a, b]


def test_merge_candidates_dedups_reemit() -> None:
    """동일 후보 재emit (하류 full-state 반환) 은 중복 누적되지 않음 (멱등)."""
    a = _cand("opus", idx=0)
    b = _cand("sonnet", idx=1)
    merged = _merge_candidates([a, b], [a, b])
    assert merged == [a, b]  # 중복 없음


# ---------- qa_reviews reducer 채널 (M5 step2) ----------


def test_initial_state_qa_channels_default_empty() -> None:
    s = initial_v2_state("r", TargetAlgorithm.BFS)
    assert s.qa_reviews == []
    assert s.qa_report is None


def test_merge_qa_reviews_accumulates_distinct() -> None:
    a = QAReview(kind="ambiguity", passed=True)
    b = QAReview(kind="leakage", passed=False)
    assert _merge_qa_reviews([a], [b]) == [a, b]


def test_merge_qa_reviews_dedups_reemit() -> None:
    """4 병렬 리뷰어 fan-out 후 하류 full-state 재emit 에도 멱등 (candidates 동일)."""
    a = QAReview(kind="ambiguity", passed=True)
    b = QAReview(kind="fairness", passed=True)
    merged = _merge_qa_reviews([a, b], [a, b])
    assert merged == [a, b]
