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

from ipe.graph import _decision, _route_after_decision
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
