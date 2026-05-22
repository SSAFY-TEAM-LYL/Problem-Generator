"""SolutionAttempt + Lesson 단위 테스트 (D안 PR-A1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import Lesson, SolutionAttempt


def _valid_lesson(sig: str = "use-heapq") -> Lesson:
    return Lesson(signature=sig, content="Use heapq for priority queue.", from_iter=0)


def _valid_attempt() -> SolutionAttempt:
    return SolutionAttempt(
        code="import heapq\n\ndef solve():\n    pass\n",
        language="python",
        lessons=[_valid_lesson()],
        iteration=1,
    )


def test_solution_attempt_constructs_with_minimal_valid_input() -> None:
    attempt = _valid_attempt()
    assert attempt.language == "python"
    assert attempt.brute_code is None
    assert attempt.coder_fanout_index == 0
    assert attempt.iteration == 1


def test_solution_attempt_is_frozen() -> None:
    attempt = _valid_attempt()
    with pytest.raises(ValidationError):
        attempt.code = "mutated"


def test_solution_attempt_rejects_empty_code() -> None:
    with pytest.raises(ValidationError):
        SolutionAttempt(code="", iteration=0)


def test_solution_attempt_rejects_unknown_language() -> None:
    with pytest.raises(ValidationError):
        SolutionAttempt.model_validate(
            {"code": "x", "iteration": 0, "language": "rust"}
        )


def test_solution_attempt_accepts_java() -> None:
    attempt = SolutionAttempt(code="class Solution{}", language="java", iteration=0)
    assert attempt.language == "java"


def test_solution_attempt_negative_iteration_rejected() -> None:
    with pytest.raises(ValidationError):
        SolutionAttempt(code="x", iteration=-1)


def test_lesson_requires_non_empty_signature_and_content() -> None:
    with pytest.raises(ValidationError):
        Lesson(signature="", content="x", from_iter=0)
    with pytest.raises(ValidationError):
        Lesson(signature="s", content="", from_iter=0)


def test_solution_attempt_with_brute_code() -> None:
    attempt = SolutionAttempt(
        code="def solve(): pass",
        brute_code="def brute(): pass",
        iteration=0,
    )
    assert attempt.brute_code == "def brute(): pass"
