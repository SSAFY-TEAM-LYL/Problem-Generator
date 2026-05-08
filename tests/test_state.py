"""state.py smoke test — TypedDict 정의가 정상 import되고 인스턴스화 가능한지."""

from __future__ import annotations

from ipe.state import (
    ConstraintSpec,
    IterationRecord,
    LLMCallRecord,
    NodeRetryBudget,
    ProblemState,
)


def test_problem_state_partial_fill() -> None:
    """ProblemState는 total=False — 부분 채움 정상."""
    s: ProblemState = {}
    s["target_algorithm"] = "Two Sum"
    s["iteration_count"] = 0
    assert s["target_algorithm"] == "Two Sum"
    assert s["iteration_count"] == 0


def test_constraint_spec() -> None:
    cs: ConstraintSpec = {
        "time_limit_ms": 2000,
        "memory_limit_mb": 256,
        "raw": "1 ≤ N ≤ 100,000, 시간 2초, 메모리 256MB",
    }
    assert cs["time_limit_ms"] == 2000
    assert cs["memory_limit_mb"] == 256


def test_iteration_record() -> None:
    rec: IterationRecord = {
        "iter_index": 1,
        "node": "coder",
        "action": "fix",
        "error_signature": "wa_phase_a_idx_2",
        "feedback": "expected 3, got 5",
    }
    assert rec["node"] == "coder"
    assert rec["error_signature"] == "wa_phase_a_idx_2"


def test_llm_call_record() -> None:
    rec: LLMCallRecord = {
        "seq": 1,
        "node": "architect",
        "model": "claude-opus-4-7",
        "input_tokens": 1000,
        "output_tokens": 500,
        "cost_usd": 0.054,
        "timestamp": "2026-05-08T01:00:00Z",
    }
    assert rec["model"] == "claude-opus-4-7"
    assert rec["cost_usd"] == 0.054


def test_node_retry_budget_defaults() -> None:
    """SPEC §5 기본값 (REVIEW Q5에서 coder 3→4, max_iter 5→7로 갱신됨)."""
    budget: NodeRetryBudget = {
        "architect": 2,
        "coder": 4,
        "auditor": 2,
        "generator": 2,
    }
    assert budget["coder"] == 4
    total = budget["architect"] + budget["coder"] + budget["auditor"] + budget["generator"]
    assert total == 10
