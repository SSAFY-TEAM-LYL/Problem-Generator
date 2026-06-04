"""SolutionCandidate / ReconciliationResult 단위 테스트 (Phase 3 M2 step 1).

병렬 solution synthesis 의 fan-out 아티팩트(SolutionCandidate)와 fan-in 집계
아티팩트(ReconciliationResult)의 typed 계약 검증. 모두 frozen + extra=forbid.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import ReconciliationResult, SolutionCandidate


def test_solution_candidate_golden_minimal() -> None:
    c = SolutionCandidate(role="golden", origin="opus", code="print(1)")
    assert c.role == "golden"
    assert c.origin == "opus"
    assert c.language == "python"
    assert c.fanout_index == 0


def test_solution_candidate_brute_with_index() -> None:
    c = SolutionCandidate(
        role="brute", origin="naive", code="print(1)", fanout_index=2
    )
    assert c.role == "brute"
    assert c.fanout_index == 2


def test_solution_candidate_is_frozen() -> None:
    c = SolutionCandidate(role="golden", origin="opus", code="print(1)")
    with pytest.raises(ValidationError):
        c.code = "print(2)"  # type: ignore[misc]


def test_solution_candidate_rejects_empty_code() -> None:
    with pytest.raises(ValidationError):
        SolutionCandidate(role="golden", origin="opus", code="")


def test_solution_candidate_rejects_empty_origin() -> None:
    with pytest.raises(ValidationError):
        SolutionCandidate(role="golden", origin="", code="print(1)")


def test_solution_candidate_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        SolutionCandidate(role="reference", origin="opus", code="print(1)")  # type: ignore[arg-type]


def test_solution_candidate_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        SolutionCandidate(
            role="golden", origin="opus", code="print(1)", bogus=1  # type: ignore[call-arg]
        )


def test_solution_candidate_rejects_negative_index() -> None:
    with pytest.raises(ValidationError):
        SolutionCandidate(role="golden", origin="opus", code="print(1)", fanout_index=-1)


def test_reconciliation_agree_adopts_canonical() -> None:
    r = ReconciliationResult(
        candidate_count=3,
        all_agree=True,
        canonical_code="print(1)",
        adopted_origin="opus",
    )
    assert r.all_agree is True
    assert r.canonical_code == "print(1)"
    assert r.adopted_origin == "opus"
    assert r.disagreements == ()


def test_reconciliation_disagree_no_canonical() -> None:
    r = ReconciliationResult(
        candidate_count=2,
        all_agree=False,
        canonical_code=None,
        adopted_origin=None,
        disagreements=("opus vs naive differ on input #1",),
    )
    assert r.all_agree is False
    assert r.canonical_code is None
    assert r.adopted_origin is None
    assert len(r.disagreements) == 1


def test_reconciliation_is_frozen() -> None:
    r = ReconciliationResult(candidate_count=1, all_agree=True, canonical_code="x")
    with pytest.raises(ValidationError):
        r.all_agree = False  # type: ignore[misc]


def test_reconciliation_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ReconciliationResult(
            candidate_count=1, all_agree=True, canonical_code="x", bogus=1  # type: ignore[call-arg]
        )


def test_reconciliation_rejects_negative_count() -> None:
    with pytest.raises(ValidationError):
        ReconciliationResult(candidate_count=-1, all_agree=False, canonical_code=None)
