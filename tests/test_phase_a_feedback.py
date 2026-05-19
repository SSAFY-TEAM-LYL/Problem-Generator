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
from ipe.nodes.executor import (
    _build_phase_a_feedback,
    _decide_phase_a_route,
    _summarize_phase_a_failure,
)
from ipe.state import ProblemState


def _brute_result(
    idx: int,
    *,
    status: str = "OK",
    output: str = "",
    matches_expected: bool = False,
) -> dict:
    """R5 brute oracle result helper — _run_brute_on_samples 반환 schema."""
    return {
        "index": idx,
        "status": status,
        "output": output,
        "matches_expected": matches_expected,
    }


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


# =============================================================================
# R-phase-a-osc-break (Round 17) — Phase A routing의 architect 무한 반복 차단
# =============================================================================


def _state_with_history(records: list[dict]) -> ProblemState:
    """history만 채운 ProblemState (다른 필드 무관)."""
    return {"iteration_history": records}  # type: ignore[typeddict-item]


def _arch_history_entry(sig: str, feedback: str = "") -> dict:
    return {
        "iter_index": 1, "node": "architect", "action": "retry",
        "error_signature": sig, "feedback": feedback,
    }


class TestDecidePhaseARouteWithHistory:
    """R-phase-a-osc-break: history 인지 후 분기 (a)/(b) 무한 반복 차단."""

    def _results_partial_pass(self) -> list[dict]:
        """분기 (a) 트리거: 4/5 passed, 1 mismatched, no crash."""
        return [
            _r(idx=0, passed=True, status="OK", expected="x", actual="x"),
            _r(idx=1, passed=True, status="OK", expected="y", actual="y"),
            _r(idx=2, passed=True, status="OK", expected="z", actual="z"),
            _r(idx=3, passed=True, status="OK", expected="w", actual="w"),
            _r(idx=4, status="OK", expected="42", actual="0"),
        ]

    def _results_all_fail_unique(self) -> list[dict]:
        """분기 (b) 트리거: all fail + all OK + unique outputs."""
        return [
            _r(idx=0, status="OK", expected="1", actual="A"),
            _r(idx=1, status="OK", expected="2", actual="B"),
            _r(idx=2, status="OK", expected="3", actual="C"),
        ]

    def _results_crash(self) -> list[dict]:
        """분기 (c) 트리거: crash 포함."""
        return [
            _r(idx=0, status="RTE", stderr="boom"),
            _r(idx=1, passed=True, status="OK", expected="ok", actual="ok"),
        ]

    def test_empty_history_uses_base_routing_architect(self) -> None:
        """history 비어있으면 기존 분기 (a) → architect."""
        results = self._results_partial_pass()
        state = _state_with_history([])
        assert _decide_phase_a_route(results, state) == "architect"

    def test_one_prior_arch_same_sig_still_architect(self) -> None:
        """history에 같은 arch sig 1회 → 이번 포함 2회. 임계값 미만 (3회+ 필요)."""
        results = self._results_partial_pass()
        sig = _error_signature(_build_phase_a_feedback(results, "architect"))
        state = _state_with_history([_arch_history_entry(sig)])
        assert _decide_phase_a_route(results, state) == "architect"

    def test_two_prior_arch_same_sig_forces_coder(self) -> None:
        """history에 같은 arch sig 2회+ → 이번 포함 3회+ → coder 강제 (R-phase-a-osc-break)."""
        results = self._results_partial_pass()
        sig = _error_signature(_build_phase_a_feedback(results, "architect"))
        state = _state_with_history([
            _arch_history_entry(sig),
            _arch_history_entry(sig),
        ])
        assert _decide_phase_a_route(results, state) == "coder"

    def test_two_prior_different_sig_still_architect(self) -> None:
        """history에 다른 sig만 있으면 carry-over 없음 — base 유지."""
        results = self._results_partial_pass()
        state = _state_with_history([
            _arch_history_entry("aaaaaaaa", "different feedback"),
            _arch_history_entry("bbbbbbbb", "another one"),
        ])
        assert _decide_phase_a_route(results, state) == "architect"

    def test_two_prior_coder_same_sig_no_swap(self) -> None:
        """coder 노드의 history는 architect oscillation breaker 트리거 안 함."""
        results = self._results_partial_pass()
        sig = _error_signature(_build_phase_a_feedback(results, "architect"))
        coder_entries = [
            {"iter_index": 1, "node": "coder", "action": "retry",
             "error_signature": sig, "feedback": ""},
            {"iter_index": 2, "node": "coder", "action": "retry",
             "error_signature": sig, "feedback": ""},
        ]
        state = _state_with_history(coder_entries)
        assert _decide_phase_a_route(results, state) == "architect"

    def test_branch_b_also_subject_to_break(self) -> None:
        """분기 (b) all-fail-unique도 architect — 같은 메커니즘 적용."""
        results = self._results_all_fail_unique()
        sig = _error_signature(_build_phase_a_feedback(results, "architect"))
        state = _state_with_history([
            _arch_history_entry(sig),
            _arch_history_entry(sig),
        ])
        assert _decide_phase_a_route(results, state) == "coder"

    def test_branch_c_unaffected_by_history(self) -> None:
        """분기 (c) (crash) → 항상 coder. history 무관."""
        results = self._results_crash()
        # arch history 가득 채워도 (c)는 그대로 coder
        state = _state_with_history([
            _arch_history_entry("any") for _ in range(10)
        ])
        assert _decide_phase_a_route(results, state) == "coder"

    def test_empty_results_returns_coder(self) -> None:
        """기존 동작 보존: 빈 results → coder."""
        state = _state_with_history([])
        assert _decide_phase_a_route([], state) == "coder"

    def test_no_iteration_history_key_treated_as_empty(self) -> None:
        """state에 iteration_history 없으면 빈 list로 처리."""
        results = self._results_partial_pass()
        state: ProblemState = {}
        assert _decide_phase_a_route(results, state) == "architect"


# =============================================================================
# R5 (Round 19) — Phase A brute oracle cross-check
# =============================================================================


def _results_partial_pass_4of5() -> list[dict]:
    """4/5 pass + 1 mismatch (분기 (a) trigger). idx=4가 fail."""
    return [
        _r(idx=0, passed=True, status="OK", expected="3", actual="3"),
        _r(idx=1, passed=True, status="OK", expected="30", actual="30"),
        _r(idx=2, passed=True, status="OK", expected="12", actual="12"),
        _r(idx=3, passed=True, status="OK", expected="42", actual="42"),
        _r(idx=4, status="OK", expected="100", actual="99"),  # mismatch
    ]


class TestPhaseARouteWithBruteOracle:
    """R5: brute oracle cross-check가 routing 결정에 영향."""

    def test_no_brute_results_uses_base_routing(self) -> None:
        """brute_results=None → 기존 동작 (회귀 0)."""
        results = _results_partial_pass_4of5()
        state: ProblemState = {}
        assert _decide_phase_a_route(results, state) == "architect"
        assert _decide_phase_a_route(results, state, brute_results=None) == "architect"

    def test_brute_confirms_architect_expected_forces_coder(self) -> None:
        """R5 핵심: brute가 모든 sample에서 architect expected와 일치 (matches_expected=True 모두)
        → architect 정확, golden bug → **coder 강제** (sample-wrong 오진단 회피)."""
        results = _results_partial_pass_4of5()
        state: ProblemState = {}
        brute = [
            _brute_result(0, output="3", matches_expected=True),
            _brute_result(1, output="30", matches_expected=True),
            _brute_result(2, output="12", matches_expected=True),
            _brute_result(3, output="42", matches_expected=True),
            _brute_result(4, output="100", matches_expected=True),  # ← architect 정답 확정
        ]
        assert _decide_phase_a_route(results, state, brute_results=brute) == "coder"

    def test_brute_disagrees_with_architect_keeps_architect_routing(self) -> None:
        """brute가 다른 답 → architect routing 유지 (feedback에 brute 결과 노출)."""
        results = _results_partial_pass_4of5()
        state: ProblemState = {}
        brute = [
            _brute_result(0, output="3", matches_expected=True),
            _brute_result(1, output="30", matches_expected=True),
            _brute_result(2, output="12", matches_expected=True),
            _brute_result(3, output="42", matches_expected=True),
            _brute_result(4, output="999", matches_expected=False),  # ← architect expected와 다름
        ]
        assert _decide_phase_a_route(results, state, brute_results=brute) == "architect"

    def test_brute_compile_fail_returns_none_uses_base(self) -> None:
        """brute_results=[] (compile fail) → 기존 분기."""
        results = _results_partial_pass_4of5()
        state: ProblemState = {}
        assert _decide_phase_a_route(results, state, brute_results=[]) == "architect"

    def test_brute_with_rte_status_ignored(self) -> None:
        """brute 일부 RTE → matches_expected 신뢰 못 함, 기존 분기."""
        results = _results_partial_pass_4of5()
        state: ProblemState = {}
        brute = [
            _brute_result(0, output="3", matches_expected=True),
            _brute_result(1, status="RTE", matches_expected=False),  # crash
            _brute_result(2, output="12", matches_expected=True),
            _brute_result(3, output="42", matches_expected=True),
            _brute_result(4, output="100", matches_expected=True),
        ]
        # brute 일부 RTE → all-match 보장 못 함 → 기존 분기
        assert _decide_phase_a_route(results, state, brute_results=brute) == "architect"

    def test_brute_force_overrides_phase_a_osc_break(self) -> None:
        """R5는 R-phase-a-osc-break (history threshold 3회) 발동 전에 효과 — 1 cycle에 결정."""
        results = _results_partial_pass_4of5()
        state: ProblemState = {"iteration_history": []}  # 첫 cycle (history 비어있음)
        brute_match_all = [_brute_result(i, matches_expected=True) for i in range(5)]
        # 첫 cycle이지만 brute confirm → coder
        assert _decide_phase_a_route(results, state, brute_results=brute_match_all) == "coder"


class TestPhaseAFeedbackWithBruteOracle:
    """R5: architect routing 시 feedback에 brute 결과 enrichment."""

    def test_architect_feedback_includes_brute_output_when_disagree(self) -> None:
        """architect routing + brute가 다른 답 → feedback에 brute output 포함."""
        results = _results_partial_pass_4of5()
        brute = [
            _brute_result(0, output="3", matches_expected=True),
            _brute_result(1, output="30", matches_expected=True),
            _brute_result(2, output="12", matches_expected=True),
            _brute_result(3, output="42", matches_expected=True),
            _brute_result(4, output="999", matches_expected=False),
        ]
        fb = _build_phase_a_feedback(results, "architect", brute_results=brute)
        # 기존 메시지 보존
        assert "sample expected_output likely wrong" in fb
        # brute 정보 enrichment
        assert "brute oracle" in fb.lower() or "brute" in fb.lower()
        assert "999" in fb  # brute가 제시한 정답 후보

    def test_architect_feedback_unchanged_without_brute(self) -> None:
        """brute_results 없으면 기존 형식."""
        results = _results_partial_pass_4of5()
        fb_old = _build_phase_a_feedback(results, "architect")
        fb_no_brute = _build_phase_a_feedback(results, "architect", brute_results=None)
        assert fb_old == fb_no_brute

    def test_coder_feedback_unchanged_with_brute(self) -> None:
        """coder routing은 brute info 추가 안 함 (기존 형식 유지)."""
        results = [
            _r(idx=0, status="RTE", stderr="boom"),
            _r(idx=1, passed=True, status="OK"),
        ]
        brute = [_brute_result(i, matches_expected=True) for i in range(2)]
        fb_brute = _build_phase_a_feedback(results, "coder", brute_results=brute)
        fb_none = _build_phase_a_feedback(results, "coder")
        # coder feedback은 기존 형식 (brute 무관)
        assert "phase A failures" in fb_brute
        # brute oracle 텍스트는 coder feedback에 없음
        assert "brute" not in fb_brute.lower() or fb_brute == fb_none
