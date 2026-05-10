"""Unit tests — _executor_phases helper functions (R1: detailed feedback).

배경: v0.2.0 Sprint 1 R1 — Coder/Auditor가 ``"phase X: N cases failed"`` 만
받던 abstract feedback 구조를 보강. 본 테스트는 새 helper의 동작을
deterministic하게 검증한다 (LLM 없이 순수 로직).

검증 범위:
- ``_excerpt`` — None / 단문 / 장문 절단
- ``_build_failure_feedback`` — coder/auditor/generator role 분기 + cap
"""

from __future__ import annotations

from ipe.nodes._executor_phases import (
    _MAX_FAILURE_DETAILS,
    _build_failure_feedback,
    _excerpt,
)


class TestExcerpt:
    def test_none_returns_empty(self) -> None:
        assert _excerpt(None) == ""

    def test_empty_returns_empty(self) -> None:
        assert _excerpt("") == ""

    def test_short_returned_as_is(self) -> None:
        assert _excerpt("hello") == "hello"

    def test_long_truncated_with_ellipsis(self) -> None:
        result = _excerpt("a" * 500, limit=200)
        assert result == "a" * 200 + "..."

    def test_crlf_normalized_to_lf(self) -> None:
        assert _excerpt("foo\r\nbar") == "foo\nbar"


class TestBuildFailureFeedbackCoder:
    def test_no_failures_returns_header(self) -> None:
        msg = _build_failure_feedback(
            header="phase C: solution failed on 0 stress cases",
            failures=[],
            role="coder",
        )
        assert msg == "phase C: solution failed on 0 stress cases"

    def test_coder_includes_status_and_stderr(self) -> None:
        failures = [
            {
                "phase": "stress",
                "status": "RTE",
                "execution_time_ms": 42,
                "stderr": "IndexError: list index out of range",
                "stdin_text": "10 20 30",
                "input_bytes": 8,
                "generator": "max_n",
                "seed": 123,
            },
        ]
        msg = _build_failure_feedback(
            header="phase C: solution failed on 1 stress cases",
            failures=failures,
            role="coder",
        )
        assert "phase C: solution failed on 1 stress cases" in msg
        assert "Failing cases (first 1)" in msg
        assert "status=RTE" in msg
        assert "elapsed_ms=42" in msg
        assert "generator=max_n" in msg
        assert "seed=123" in msg
        assert "input_bytes=8" in msg
        assert "IndexError" in msg

    def test_coder_caps_at_max_details(self) -> None:
        failures = [
            {"phase": "stress", "status": "TLE", "execution_time_ms": i,
             "stderr": f"err{i}"}
            for i in range(5)
        ]
        msg = _build_failure_feedback(
            header="phase C: solution failed on 5 stress cases",
            failures=failures,
            role="coder",
        )
        assert "first 3" in msg
        assert "err0" in msg
        assert "err2" in msg
        assert "err4" not in msg
        assert _MAX_FAILURE_DETAILS == 3

    def test_coder_excerpts_long_stderr(self) -> None:
        long_err = "x" * 500
        failures = [{"phase": "stress", "status": "RTE",
                     "execution_time_ms": 0, "stderr": long_err}]
        msg = _build_failure_feedback(
            header="phase C: solution failed on 1 stress cases",
            failures=failures,
            role="coder",
        )
        assert "x" * 200 + "..." in msg
        assert long_err not in msg

    def test_coder_falls_back_to_input_field(self) -> None:
        failures = [{"phase": "adversarial", "status": "WA",
                     "execution_time_ms": 1, "stderr": "", "input": "1 2 3"}]
        msg = _build_failure_feedback(
            header="phase B: solution failed on 1 adversarial cases",
            failures=failures,
            role="coder",
        )
        assert "input: '1 2 3'" in msg


class TestBuildFailureFeedbackAuditor:
    def test_auditor_shows_violated_input_with_reason(self) -> None:
        failures = [
            {"phase": "adversarial", "index": 0, "input": "100 200",
             "validator_error": "N out of range [1,10]"},
        ]
        msg = _build_failure_feedback(
            header="phase B: 1 adversarial inputs violate constraints",
            failures=failures,
            role="auditor",
        )
        assert "phase B: 1 adversarial inputs violate constraints" in msg
        assert "Violating adversarial inputs" in msg
        assert "N out of range" in msg
        assert "100 200" in msg

    def test_auditor_default_reason(self) -> None:
        failures = [{"input": "999"}]
        msg = _build_failure_feedback(
            header="phase B: 1 adversarial inputs violate constraints",
            failures=failures,
            role="auditor",
        )
        assert "constraint violated" in msg


class TestBuildFailureFeedbackGenerator:
    def test_generator_shows_script_error(self) -> None:
        failures = [
            {"generator": "lis_input", "seed": 42,
             "stderr": "SyntaxError: invalid syntax"},
        ]
        msg = _build_failure_feedback(
            header="phase C: 1 generator scripts failed",
            failures=failures,
            role="generator",
        )
        assert "Failing generator scripts" in msg
        assert "generator=lis_input" in msg
        assert "seed=42" in msg
        assert "SyntaxError" in msg
