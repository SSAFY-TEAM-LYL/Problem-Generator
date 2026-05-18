"""R-sig-detail — Phase A coder routing feedback의 signature granularity unit.

배경 (Round 12 e2e 측정):
- 기존: `"phase A failures: 4/4"` — failures/total 카운트만
- `_error_signature(feedback)` = SHA-1(feedback)[:12] → 같은 X/Y면 같은 sig
- R-coder-osc swap 후에도 새 problem이 동일 X/Y로 fail하면 sig 같음 →
  oscillation_break 매 cycle 발동하지만 effective fix 아님

해법: coder routing feedback에 실패 sample의 핵심 정보 (idx, status,
expected/actual 짧은 prefix)를 포함하여 sig가 problem-specific해지도록.

스펙: CHANGES.md §18 (Round 13), docs/improvements/2026-05-18_sig-detail.md
"""

from __future__ import annotations

from ipe.graph import _error_signature
from ipe.nodes.executor import _build_phase_a_feedback, _summarize_phase_a_failure


def _r(*, idx: int, status: str = "OK", passed: bool = False,
       expected: str = "", actual: str = "", stderr: str = "") -> dict:
    """Phase A result dict — executor.py:151-160 schema."""
    return {
        "phase": "sample",
        "index": idx,
        "pass": passed,
        "status": status,
        "execution_time_ms": 12,
        "expected": expected,
        "actual": actual,
        "stderr": stderr,
    }


class TestSummarizePhaseAFailure:
    """single result → 짧은 사람-읽기-가능 + signature-friendly 문자열."""

    def test_ok_status_includes_expected_and_actual(self) -> None:
        s = _summarize_phase_a_failure(_r(idx=0, status="OK", expected="3", actual="0"))
        assert "idx=0" in s
        assert "OK" in s
        assert "'3'" in s   # expected
        assert "'0'" in s   # actual

    def test_rte_status_includes_stderr(self) -> None:
        s = _summarize_phase_a_failure(
            _r(idx=2, status="RTE", stderr="IndexError: list out of range")
        )
        assert "idx=2" in s
        assert "RTE" in s
        assert "IndexError" in s

    def test_tle_status_includes_status(self) -> None:
        s = _summarize_phase_a_failure(_r(idx=1, status="TLE", stderr=""))
        assert "TLE" in s

    def test_long_expected_truncated(self) -> None:
        big = "x" * 500
        s = _summarize_phase_a_failure(_r(idx=0, status="OK", expected=big, actual="0"))
        # 전체 feedback 길이가 LLM prompt 부담이 되지 않도록 truncate
        assert len(s) < 200

    def test_newlines_in_expected_normalized(self) -> None:
        """expected/actual 안의 \\n은 한 줄 표현 처리 — feedback이 multi-line으로 깨지지 않도록."""
        s = _summarize_phase_a_failure(_r(idx=0, status="OK",
                                           expected="line1\nline2", actual="line1\nline3"))
        # repr() 사용 시 escape됨, replace 사용 시 공백 변환 — 둘 다 OK
        assert "\n" not in s or "\\n" in s


class TestBuildPhaseAFeedbackCoderRouting:
    """coder routing 시 feedback에 실패 sample 요약 포함 → signature granularity 확보."""

    def test_coder_routing_includes_failure_count(self) -> None:
        """기존 형식 보존: 'phase A failures: X/Y'."""
        results = [
            _r(idx=0, status="OK", expected="3", actual="0"),
            _r(idx=1, status="OK", expected="30", actual="0"),
        ]
        fb = _build_phase_a_feedback(results, "coder")
        assert "phase A failures: 2/2" in fb

    def test_coder_routing_includes_failure_details(self) -> None:
        """R-sig-detail 핵심: feedback에 각 실패 sample의 idx + expected + actual 포함."""
        results = [
            _r(idx=0, status="OK", expected="3", actual="0"),
            _r(idx=1, status="OK", expected="30", actual="0"),
        ]
        fb = _build_phase_a_feedback(results, "coder")
        assert "idx=0" in fb
        assert "idx=1" in fb
        assert "'3'" in fb
        assert "'30'" in fb

    def test_different_problems_yield_different_signatures(self) -> None:
        """핵심 회귀 방지: 같은 4/4 카운트라도 expected/actual이 다르면 sig 달라야 함.

        R-coder-osc swap 후 architect가 새 problem 생성 → 같은 fail 카운트
        (예: 5/5)지만 다른 expected/actual → sig 변화 → oscillation_break 해소.
        """
        problem_a = [
            _r(idx=0, status="OK", expected="3", actual="0"),
            _r(idx=1, status="OK", expected="30", actual="0"),
            _r(idx=2, status="OK", expected="12", actual="0"),
            _r(idx=3, status="OK", expected="42", actual="0"),
        ]
        problem_b = [
            _r(idx=0, status="OK", expected="hello world", actual="empty"),
            _r(idx=1, status="OK", expected="100", actual="empty"),
            _r(idx=2, status="OK", expected="abc", actual="empty"),
            _r(idx=3, status="OK", expected="xyz", actual="empty"),
        ]
        fb_a = _build_phase_a_feedback(problem_a, "coder")
        fb_b = _build_phase_a_feedback(problem_b, "coder")
        sig_a = _error_signature(fb_a)
        sig_b = _error_signature(fb_b)
        assert sig_a != sig_b, "다른 problem → 다른 sig여야 함"

    def test_same_problem_yields_same_signature(self) -> None:
        """결정성 보존: 동일 results → 동일 sig (R-coder-osc 정상 발동 조건)."""
        results_1 = [_r(idx=0, status="OK", expected="3", actual="0")]
        results_2 = [_r(idx=0, status="OK", expected="3", actual="0")]
        assert _error_signature(_build_phase_a_feedback(results_1, "coder")) == \
               _error_signature(_build_phase_a_feedback(results_2, "coder"))

    def test_only_failed_samples_included(self) -> None:
        """통과한 sample은 feedback details에서 제외 (LLM이 통과한 것까지 다시 쓰지 않도록)."""
        results = [
            _r(idx=0, passed=True, status="OK", expected="3", actual="3"),
            _r(idx=1, status="OK", expected="30", actual="0"),
        ]
        fb = _build_phase_a_feedback(results, "coder")
        assert "phase A failures: 1/2" in fb
        assert "idx=1" in fb
        # passed sample idx=0의 expected="3"는 detail에 포함되지 않아야 함
        # — 단, target=="architect" 분기로 갈 수도 있어서 본 테스트는 coder forcing
        # 검증: idx=0이 detail 영역(괄호 안)에 없음
        details = fb.split("[", 1)[1] if "[" in fb else fb
        assert "idx=0" not in details


class TestBuildPhaseAFeedbackArchitectRoutingPreserved:
    """architect routing 분기는 기존 형식 유지 (회귀 0)."""

    def test_architect_partial_pass_format_unchanged(self) -> None:
        results = [
            _r(idx=0, passed=True, status="OK", expected="3", actual="3"),
            _r(idx=1, status="OK", expected="30", actual="0"),
        ]
        fb = _build_phase_a_feedback(results, "architect")
        assert "phase A: 1/2 passed but 1 mismatched" in fb
        assert "sample expected_output likely wrong" in fb

    def test_architect_all_fail_unique_format_unchanged(self) -> None:
        results = [
            _r(idx=0, status="OK", expected="3", actual="0"),
            _r(idx=1, status="OK", expected="30", actual="1"),
        ]
        fb = _build_phase_a_feedback(results, "architect")
        assert "phase A: all 2 failed" in fb
        assert "consistent unique outputs" in fb
        assert "samples likely wrong" in fb
