"""QA 아티팩트 스키마 단위 테스트 (Phase 3 M5 step1).

QAReview(리뷰어 1종 산출) + QAReport(aggregator 산출) — frozen/forbid 컨벤션,
passed↔blocker 모순 validator, overall_pass/failed_kinds 집계 property.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import QAFinding, QAReport, QAReview


def _review(
    kind: str = "ambiguity",
    *,
    passed: bool = True,
    findings: tuple[QAFinding, ...] = (),
) -> QAReview:
    return QAReview(kind=kind, passed=passed, findings=findings)  # type: ignore[arg-type]


# ---------- QAFinding ----------


def test_finding_requires_nonempty_description() -> None:
    with pytest.raises(ValidationError):
        QAFinding(severity="warning", description="")


def test_finding_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        QAFinding(severity="catastrophic", description="x")  # type: ignore[arg-type]


# ---------- QAReview ----------


def test_review_is_frozen_and_forbids_extra() -> None:
    review = _review()
    with pytest.raises(ValidationError):
        review.passed = False  # type: ignore[misc]
    with pytest.raises(ValidationError):
        QAReview(kind="fairness", passed=True, bogus="x")  # type: ignore[call-arg]


def test_review_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        _review("vibes")


def test_review_passed_with_blocker_finding_is_contradiction() -> None:
    blocker = QAFinding(severity="blocker", description="유명 문제와 동형")
    with pytest.raises(ValidationError, match="blocker"):
        _review("leakage", passed=True, findings=(blocker,))


def test_review_failed_with_blocker_is_valid() -> None:
    blocker = QAFinding(severity="blocker", description="모호한 출력 형식")
    review = _review("ambiguity", passed=False, findings=(blocker,))
    assert review.passed is False
    assert review.findings[0].severity == "blocker"


def test_review_passed_with_warning_finding_is_valid() -> None:
    warning = QAFinding(severity="warning", description="경계 서술이 다소 장황")
    review = _review("fairness", passed=True, findings=(warning,))
    assert review.passed is True


# ---------- QAReport ----------


def test_report_requires_at_least_one_review() -> None:
    with pytest.raises(ValidationError):
        QAReport(reviews=())


def test_report_overall_pass_when_all_pass() -> None:
    report = QAReport(
        reviews=(
            _review("ambiguity"),
            _review("fairness"),
            _review("leakage"),
            _review("difficulty"),
        )
    )
    assert report.overall_pass is True
    assert report.failed_kinds == ()


def test_report_overall_fail_and_failed_kinds_when_any_fails() -> None:
    report = QAReport(
        reviews=(
            _review("ambiguity"),
            _review("leakage", passed=False),
            _review("difficulty", passed=False),
        )
    )
    assert report.overall_pass is False
    assert report.failed_kinds == ("leakage", "difficulty")
