"""Routing 단위 테스트 — graph 우회 직접 호출 (P7 audit B1 분할).

스펙: ARCHITECTURE.md §3.4, IMPLEMENTATION_ROADMAP §1 P7.4
근거: ``tests/integration/test_routing.py`` 422 lines > budget ≤400 위반 →
단위 테스트(graph 우회 함수 직접 호출)는 별도 파일로 분리.

검증 대상:
- ``ipe.graph._decision`` — halt 가드 우선순위 + budget 차감 + history 추가
- ``ipe.graph._route_after_decision`` — conditional_edges 분기 함수
- ``ipe.nodes._history.build_history_section`` — markdown 변환 + oscillation 경고
"""

from __future__ import annotations

import pytest
from langgraph.graph import END

from ipe.graph import (
    _decision,
    _detect_architect_oscillation,
    _error_signature,
    _route_after_decision,
)
from ipe.nodes._history import build_history_section
from ipe.state import ProblemState


def _default_budget() -> dict[str, int]:
    return {"architect": 2, "coder": 4, "auditor": 2, "generator": 2}


# =============================================================================
# _decision — halt 가드 우선순위
# =============================================================================


class TestDecision:
    def test_cost_exceeded_short_circuits(self) -> None:
        """누적 cost > max_cost_usd → cost_exceeded (가장 높은 우선순위)."""
        state: ProblemState = {
            "max_cost_usd": 0.01,
            "llm_calls": [
                {"cost_usd": 0.005, "node": "architect", "seq": 0,
                 "input_tokens": 0, "output_tokens": 0, "model": "x", "timestamp": ""},
                {"cost_usd": 0.02, "node": "coder", "seq": 1,
                 "input_tokens": 0, "output_tokens": 0, "model": "x", "timestamp": ""},
            ],
            "iteration_count": 0,
            "max_iter": 5,
            "node_retry_budget": _default_budget(),  # type: ignore[typeddict-item]
            "last_failed_node": "coder",
        }
        result = _decision(state)
        assert result["final_status"] == "cost_exceeded"
        assert "cost guard" in (result.get("feedback_message") or "")

    def test_success_preserved(self) -> None:
        """executor가 set한 final_status='success'는 보존."""
        state: ProblemState = {
            "final_status": "success",
            "max_cost_usd": 100.0,
            "llm_calls": [],
            "iteration_count": 1,
            "max_iter": 5,
        }
        result = _decision(state)
        assert result["final_status"] == "success"

    def test_max_iter_halt(self) -> None:
        """iteration_count >= max_iter → max_iterations."""
        state: ProblemState = {
            "iteration_count": 5,
            "max_iter": 5,
            "max_cost_usd": 100.0,
            "llm_calls": [],
            "last_failed_node": "coder",
            "node_retry_budget": _default_budget(),  # type: ignore[typeddict-item]
        }
        result = _decision(state)
        assert result["final_status"] == "max_iterations"

    def test_budget_exhausted(self) -> None:
        """node_retry_budget[failed] <= 0 → budget_exhausted."""
        budget = _default_budget()
        budget["coder"] = 0
        state: ProblemState = {
            "iteration_count": 1,
            "max_iter": 5,
            "max_cost_usd": 100.0,
            "llm_calls": [],
            "last_failed_node": "coder",
            "node_retry_budget": budget,  # type: ignore[typeddict-item]
        }
        result = _decision(state)
        assert result["final_status"] == "budget_exhausted"
        assert "coder" in (result.get("feedback_message") or "")

    def test_retry_decrements_budget_and_appends_history(self) -> None:
        """정상 retry — budget 차감 + iteration_history 추가."""
        budget = _default_budget()
        state: ProblemState = {
            "iteration_count": 1,
            "max_iter": 5,
            "max_cost_usd": 100.0,
            "llm_calls": [],
            "last_failed_node": "coder",
            "feedback_message": "compile error: foo",
            "node_retry_budget": budget,  # type: ignore[typeddict-item]
            "iteration_history": [],
        }
        result = _decision(state)

        assert result.get("final_status") is None  # halt 아님
        assert result["node_retry_budget"]["coder"] == 3  # 4 → 3
        history = result.get("iteration_history") or []
        assert len(history) == 1
        assert history[0]["node"] == "coder"
        assert history[0]["error_signature"]  # SHA-1 12자
        assert history[0]["feedback"] == "compile error: foo"


# =============================================================================
# _route_after_decision — conditional_edges 분기
# =============================================================================


class TestRouteAfterDecision:
    def test_success_routes_to_evaluator(self) -> None:
        """final_status='success'는 evaluator로 라우팅 (P9.3)."""
        state: ProblemState = {"final_status": "success"}
        assert _route_after_decision(state) == "evaluator"

    def test_halt_status_routes_to_end(self) -> None:
        """max_iterations / budget_exhausted / cost_exceeded → END (evaluator 우회)."""
        for status in ("max_iterations", "budget_exhausted", "cost_exceeded"):
            state: ProblemState = {"final_status": status}  # type: ignore[typeddict-item]
            assert _route_after_decision(state) == END

    @pytest.mark.parametrize(
        "node", ["architect", "coder", "auditor", "generator"]
    )
    def test_failed_node_routes_to_node(self, node: str) -> None:
        state: ProblemState = {"last_failed_node": node}
        assert _route_after_decision(state) == node

    def test_no_failure_no_status_routes_to_end(self) -> None:
        """이상 상태 — 안전하게 END."""
        assert _route_after_decision({}) == END


# =============================================================================
# build_history_section — markdown + oscillation 경고
# =============================================================================


class TestBuildHistorySection:
    def test_empty_returns_blank(self) -> None:
        assert build_history_section({}, current_node="coder") == ""

    def test_renders_recent_entries(self) -> None:
        state: ProblemState = {
            "iteration_history": [
                {
                    "iter_index": 1, "node": "coder", "action": "retry",
                    "error_signature": "abc123", "feedback": "compile error",
                },
            ],
        }
        section = build_history_section(state, current_node="coder")
        assert "Previous Attempts" in section
        assert "[iter 1]" in section
        assert "abc123" in section
        assert "compile error" in section

    def test_oscillation_warning_on_repeated_signature(self) -> None:
        """같은 (current_node, error_signature) 2회 → 강한 경고."""
        state: ProblemState = {
            "iteration_history": [
                {"iter_index": 1, "node": "coder", "action": "retry",
                 "error_signature": "sigX", "feedback": "fail"},
                {"iter_index": 2, "node": "coder", "action": "retry",
                 "error_signature": "sigX", "feedback": "fail"},
            ],
        }
        section = build_history_section(state, current_node="coder")
        assert "DIFFERENT STRATEGY REQUIRED" in section
        assert "sigX" in section

    def test_no_warning_when_signature_belongs_to_other_node(self) -> None:
        """auditor의 반복 시그니처는 coder의 prompt에 경고 안 띄움."""
        state: ProblemState = {
            "iteration_history": [
                {"iter_index": 1, "node": "auditor", "action": "retry",
                 "error_signature": "sigA", "feedback": "f1"},
                {"iter_index": 2, "node": "auditor", "action": "retry",
                 "error_signature": "sigA", "feedback": "f1"},
            ],
        }
        section = build_history_section(state, current_node="coder")
        assert "DIFFERENT STRATEGY REQUIRED" not in section


# =============================================================================
# R-osc-break — _detect_architect_oscillation + _decision 결정적 라우팅
# =============================================================================


class TestDetectArchitectOscillation:
    """architect signature 2회+ → coder 강제 라우팅 trigger 감지 (prompt-only W4의 결정적 보완)."""

    def test_no_history_returns_false(self) -> None:
        state: ProblemState = {"last_failed_node": "architect"}
        assert _detect_architect_oscillation(state, "sigX") is False

    def test_failed_node_not_architect_returns_false(self) -> None:
        """coder 실패면 architect oscillation 감지 대상 아님."""
        state: ProblemState = {
            "last_failed_node": "coder",
            "iteration_history": [
                {"iter_index": 1, "node": "architect", "action": "retry",
                 "error_signature": "sigX", "feedback": "f"},
            ],
        }
        assert _detect_architect_oscillation(state, "sigX") is False

    def test_empty_signature_returns_false(self) -> None:
        """signature가 빈 문자열이면 False (잘못된 비교 방지)."""
        state: ProblemState = {
            "last_failed_node": "architect",
            "iteration_history": [
                {"iter_index": 1, "node": "architect", "action": "retry",
                 "error_signature": "", "feedback": ""},
            ],
        }
        assert _detect_architect_oscillation(state, "") is False

    def test_different_signature_returns_false(self) -> None:
        """signature가 다르면 oscillation 아님 (정상 retry)."""
        state: ProblemState = {
            "last_failed_node": "architect",
            "iteration_history": [
                {"iter_index": 1, "node": "architect", "action": "retry",
                 "error_signature": "sigA", "feedback": "fA"},
            ],
        }
        assert _detect_architect_oscillation(state, "sigB") is False

    def test_same_architect_signature_once_in_history_returns_true(self) -> None:
        """history에 같은 architect signature 1회 + 이번 cycle = 2회 → True."""
        state: ProblemState = {
            "last_failed_node": "architect",
            "iteration_history": [
                {"iter_index": 1, "node": "architect", "action": "retry",
                 "error_signature": "sigX", "feedback": "f"},
            ],
        }
        assert _detect_architect_oscillation(state, "sigX") is True

    def test_coder_signature_match_ignored(self) -> None:
        """history의 coder 노드 같은 signature는 architect oscillation 아님."""
        state: ProblemState = {
            "last_failed_node": "architect",
            "iteration_history": [
                {"iter_index": 1, "node": "coder", "action": "retry",
                 "error_signature": "sigX", "feedback": "f"},
            ],
        }
        assert _detect_architect_oscillation(state, "sigX") is False


class TestDecisionOscillationBreaker:
    """_decision이 oscillation 감지 시 last_failed_node를 architect→coder swap."""

    def test_first_architect_failure_no_swap(self) -> None:
        """첫 architect 실패는 oscillation 아님 — 정상 architect retry."""
        state: ProblemState = {
            "iteration_count": 1,
            "max_iter": 5,
            "max_cost_usd": 100.0,
            "llm_calls": [],
            "last_failed_node": "architect",
            "feedback_message": "Architect JSON parse error: foo",
            "node_retry_budget": _default_budget(),  # type: ignore[typeddict-item]
            "iteration_history": [],
        }
        result = _decision(state)
        assert result.get("final_status") is None
        assert result["last_failed_node"] == "architect"
        assert result["node_retry_budget"]["architect"] == 1  # 2 → 1
        assert result["node_retry_budget"]["coder"] == 4  # 그대로
        history = result.get("iteration_history") or []
        assert len(history) == 1
        assert history[0]["node"] == "architect"
        assert history[0]["action"] == "retry"

    def test_second_same_signature_triggers_swap_to_coder(self) -> None:
        """같은 architect signature 2회 → last_failed_node="coder" swap, coder budget 차감."""
        feedback = "Architect JSON parse error: foo"
        sig = _error_signature(feedback)
        state: ProblemState = {
            "iteration_count": 2,
            "max_iter": 5,
            "max_cost_usd": 100.0,
            "llm_calls": [],
            "last_failed_node": "architect",
            "feedback_message": feedback,
            "node_retry_budget": _default_budget(),  # type: ignore[typeddict-item]
            "iteration_history": [
                {"iter_index": 1, "node": "architect", "action": "retry",
                 "error_signature": sig, "feedback": feedback},
            ],
        }
        result = _decision(state)
        assert result.get("final_status") is None
        # swap: routing target now coder
        assert result["last_failed_node"] == "coder"
        # coder budget 차감, architect budget 보존
        assert result["node_retry_budget"]["coder"] == 3  # 4 → 3
        assert result["node_retry_budget"]["architect"] == 2  # 보존
        # history에 oscillation_break action 기록
        history = result.get("iteration_history") or []
        assert len(history) == 2
        assert history[-1]["node"] == "architect"  # 원인 노드는 architect
        assert history[-1]["action"] == "oscillation_break"
        assert history[-1]["error_signature"] == sig

    def test_swap_then_route_to_coder(self) -> None:
        """swap 후 _route_after_decision은 coder로 라우팅."""
        feedback = "Architect output missing fields"
        sig = _error_signature(feedback)
        state: ProblemState = {
            "iteration_count": 2,
            "max_iter": 5,
            "max_cost_usd": 100.0,
            "llm_calls": [],
            "last_failed_node": "architect",
            "feedback_message": feedback,
            "node_retry_budget": _default_budget(),  # type: ignore[typeddict-item]
            "iteration_history": [
                {"iter_index": 1, "node": "architect", "action": "retry",
                 "error_signature": sig, "feedback": feedback},
            ],
        }
        decided = _decision(state)
        assert _route_after_decision(decided) == "coder"

    def test_swap_with_coder_budget_zero_triggers_exhausted(self) -> None:
        """swap 대상 coder budget=0이면 budget_exhausted(coder)."""
        feedback = "Architect repeats"
        sig = _error_signature(feedback)
        budget = _default_budget()
        budget["coder"] = 0
        state: ProblemState = {
            "iteration_count": 2,
            "max_iter": 5,
            "max_cost_usd": 100.0,
            "llm_calls": [],
            "last_failed_node": "architect",
            "feedback_message": feedback,
            "node_retry_budget": budget,  # type: ignore[typeddict-item]
            "iteration_history": [
                {"iter_index": 1, "node": "architect", "action": "retry",
                 "error_signature": sig, "feedback": feedback},
            ],
        }
        result = _decision(state)
        assert result["final_status"] == "budget_exhausted"
        assert "coder" in (result.get("feedback_message") or "")

    def test_different_signature_no_swap(self) -> None:
        """architect가 다른 signature로 실패 = 정상 retry, swap 안 함."""
        prev_feedback = "Architect JSON parse error: foo"
        prev_sig = _error_signature(prev_feedback)
        cur_feedback = "constraints_structured invalid: time_limit_ms required"
        state: ProblemState = {
            "iteration_count": 2,
            "max_iter": 5,
            "max_cost_usd": 100.0,
            "llm_calls": [],
            "last_failed_node": "architect",
            "feedback_message": cur_feedback,
            "node_retry_budget": _default_budget(),  # type: ignore[typeddict-item]
            "iteration_history": [
                {"iter_index": 1, "node": "architect", "action": "retry",
                 "error_signature": prev_sig, "feedback": prev_feedback},
            ],
        }
        result = _decision(state)
        assert result["last_failed_node"] == "architect"  # 그대로
        assert result["node_retry_budget"]["architect"] == 1  # 차감
        assert result["node_retry_budget"]["coder"] == 4  # 보존
