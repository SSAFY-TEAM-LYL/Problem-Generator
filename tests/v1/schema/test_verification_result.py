"""VerificationResult + 부속 모델 단위 테스트 (D안 PR-A1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import (
    FailureMode,
    InvariantViolation,
    SampleResult,
    StructuredFeedback,
    VerificationResult,
)


def _passing_sample(idx: int = 0) -> SampleResult:
    return SampleResult(
        index=idx,
        passed=True,
        expected_output="42",
        actual_output="42",
        elapsed_ms=12,
    )


def test_verification_result_pass_path() -> None:
    result = VerificationResult(
        overall_pass=True,
        failure_mode=FailureMode.NONE,
        sample_results=[_passing_sample(0), _passing_sample(1)],
        iteration=2,
    )
    assert result.overall_pass is True
    assert result.failure_mode == FailureMode.NONE
    assert result.feedback is None
    assert len(result.sample_results) == 2


def test_verification_result_fail_with_feedback() -> None:
    feedback = StructuredFeedback(
        target_node="coder",
        actionable_hint="Reset dist[s]=0 before pushing to heap.",
        blocking_signature="dijkstra-init-bug",
    )
    result = VerificationResult(
        overall_pass=False,
        failure_mode=FailureMode.SAMPLE_MISMATCH,
        sample_results=[
            SampleResult(
                index=0,
                passed=False,
                expected_output="5",
                actual_output="0",
                elapsed_ms=8,
            ),
        ],
        feedback=feedback,
        iteration=1,
    )
    assert result.overall_pass is False
    assert result.feedback is not None
    assert result.feedback.target_node == "coder"


def test_failure_mode_string_values() -> None:
    assert FailureMode.SAMPLE_MISMATCH.value == "sample_mismatch"
    assert FailureMode.INVARIANT_VIOLATION.value == "invariant_violation"


def test_verification_result_is_frozen() -> None:
    result = VerificationResult(
        overall_pass=True, failure_mode=FailureMode.NONE, iteration=0
    )
    with pytest.raises(ValidationError):
        result.overall_pass = False


def test_structured_feedback_rejects_empty_target_node() -> None:
    with pytest.raises(ValidationError):
        StructuredFeedback(
            target_node="",
            actionable_hint="hint",
            blocking_signature="sig",
        )


def test_invariant_violation_evidence_is_string_dict() -> None:
    violation = InvariantViolation(
        invariant_kind="non_negative_distance",
        description="d[2] = -1",
        evidence={"input": "3 2 0 2\n0 1 -1\n1 2 -1", "output": "-2"},
    )
    assert violation.evidence["input"].startswith("3 2")
    assert violation.evidence["output"] == "-2"


def test_sample_result_rejects_negative_elapsed() -> None:
    with pytest.raises(ValidationError):
        SampleResult(
            index=0,
            passed=True,
            expected_output="",
            actual_output="",
            elapsed_ms=-1,
        )
