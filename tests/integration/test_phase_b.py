"""Phase B 통합 테스트 (P5.4).

Auditor + Executor Phase B + syntactic validator 시나리오:
1. happy path — 8 valid adversarial → ``final_status='success'`` + testcases 채움
2. validator violation 우세 (5/8 out of range) → ``auditor`` 라우팅
3. solution RTE on valid inputs → ``coder`` 라우팅
4. auditor가 8개 미만 반환 → auditor self-loop (P5.1 검증, 통합)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.nodes import auditor, executor
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.state import ProblemState


def _make_tracker(tmp_path: Path) -> LLMCallTracker:
    return LLMCallTracker("test-run", tmp_path / "traces")


def _make_chat(content: str) -> MagicMock:
    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    chat.temperature = None
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": 0, "output_tokens": 0}
    chat.invoke.return_value = resp
    return chat


def _patch_chat(monkeypatch: pytest.MonkeyPatch, target: str, content: str) -> None:
    monkeypatch.setattr(target, lambda *a, **k: _make_chat(content))


def _adv_response(inputs: list[dict[str, Any]]) -> str:
    body = {"adversarial_inputs": inputs}
    return f"```json\n{json.dumps(body)}\n```"


# 8 valid adversarial inputs — A+B (1 ≤ a, b ≤ 1e9) 기준
VALID_ADV_8: list[dict[str, Any]] = [
    {"input": "1 1\n", "category": "MIN_SIZE", "reason": "smallest"},
    {"input": "1000000000 1000000000\n", "category": "BOUNDARY_HIGH", "reason": "max"},
    {"input": "1 1000000000\n", "category": "BOUNDARY_LOW", "reason": "low+high"},
    {"input": "5 5\n", "category": "UNIFORM", "reason": "equal"},
    {"input": "100 200\n", "category": "ADVERSARIAL", "reason": "regular"},
    {"input": "999999999 1\n", "category": "BOUNDARY_HIGH", "reason": "near max"},
    {"input": "2 3\n", "category": "MIN_SIZE", "reason": "near min"},
    {"input": "500 500\n", "category": "UNIFORM", "reason": "midrange"},
]


def _problem_state_with_solution() -> ProblemState:
    """architect + coder가 채운 state — Phase B 진입 준비."""
    return {
        "target_algorithm": "A+B",
        "target_language": "python",
        "problem_description": "Read two integers and print their sum.",
        "constraints": "1 <= a, b <= 1e9",
        "constraints_structured": {
            "variables": [
                {"name": "a", "min": 1, "max": 10**9, "type": "int"},
                {"name": "b", "min": 1, "max": 10**9, "type": "int"},
            ],
            "time_limit_ms": 2000,
            "memory_limit_mb": 256,
        },
        "sample_testcases": [
            {"input": "1 2\n", "expected_output": "3"},
            {"input": "10 20\n", "expected_output": "30"},
        ],
        "solution_code": "a, b = map(int, input().split())\nprint(a + b)",
    }


# =============================================================================
# 1. Happy path
# =============================================================================


def test_phase_b_happy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """8 valid adversarial → 모두 OK → final_status='success' + testcases 채움."""
    _patch_chat(
        monkeypatch, "ipe.nodes.auditor.get_chat", _adv_response(VALID_ADV_8)
    )

    tracker = _make_tracker(tmp_path)
    state = _problem_state_with_solution()

    state = auditor.run(state, tracker=tracker)
    assert "adversarial_inputs" in state
    assert len(state["adversarial_inputs"]) == 8

    state = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    assert state["final_status"] == "success"
    assert state["last_failed_node"] is None

    # testcases: 2 sample + 8 adversarial = 10
    testcases = state.get("testcases") or []
    assert len(testcases) == 10
    sample_count = sum(1 for t in testcases if t.get("kind") == "sample")
    adv_count = sum(1 for t in testcases if t.get("kind") == "adversarial")
    assert sample_count == 2
    assert adv_count == 8

    # adversarial testcase에는 expected_output (oracle)이 채워져야 함
    adv_tcs = [t for t in testcases if t.get("kind") == "adversarial"]
    assert all("expected_output" in t for t in adv_tcs)
    # "1 1\n" → "2" (1+1)
    first_adv = next(t for t in adv_tcs if t["input"] == "1 1\n")
    assert first_adv["expected_output"] == "2"


# =============================================================================
# 2. Validator violation (auditor 라우팅)
# =============================================================================


def test_phase_b_validator_violation_routes_to_auditor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """5/8 inputs가 constraints 위반 → validator failure 우세 → auditor."""
    bad_inputs: list[dict[str, Any]] = [
        {"input": "1 2\n", "category": "MIN_SIZE"},  # OK
        {"input": "0 50\n", "category": "BOUNDARY_LOW"},  # 0 < min=1
        {"input": "-5 100\n", "category": "ADVERSARIAL"},  # -5 < min=1
        {"input": "9999999999 1\n", "category": "BOUNDARY_HIGH"},  # > max
        {"input": "1 9999999999\n", "category": "BOUNDARY_HIGH"},  # > max
        {"input": "5 -100\n", "category": "ADVERSARIAL"},  # -100 < min
        {"input": "10 20\n", "category": "ADVERSARIAL"},  # OK
        {"input": "100 200\n", "category": "ADVERSARIAL"},  # OK
    ]
    _patch_chat(
        monkeypatch, "ipe.nodes.auditor.get_chat", _adv_response(bad_inputs)
    )

    tracker = _make_tracker(tmp_path)
    state = _problem_state_with_solution()
    state = auditor.run(state, tracker=tracker)
    state = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    assert state["last_failed_node"] == "auditor"
    feedback = state.get("feedback_message") or ""
    assert "violate constraints" in feedback


# =============================================================================
# 3. Solution RTE → coder 라우팅
# =============================================================================



def test_phase_b_execution_failure_routes_to_coder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """sample은 통과 (Phase A) + adversarial 일부에서 RTE → Phase B coder 라우팅.

    solution은 ``a > 999``일 때만 raise — sample (1+2, 10+20)은 모두 a≤10이라 통과,
    adversarial의 큰 값들 (1e9, 999999999 등) 일부만 RTE 유발.
    """
    _patch_chat(
        monkeypatch, "ipe.nodes.auditor.get_chat", _adv_response(VALID_ADV_8)
    )

    tracker = _make_tracker(tmp_path)
    state = _problem_state_with_solution()
    # Phase A는 통과하지만 adversarial의 큰 a값에서만 RTE 발생
    state["solution_code"] = (
        "a, b = map(int, input().split())\n"
        "if a > 999:\n"
        "    raise RuntimeError('big a')\n"
        "print(a + b)\n"
    )

    state = auditor.run(state, tracker=tracker)
    state = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    assert state["last_failed_node"] == "coder"
    feedback = state.get("feedback_message") or ""
    assert "solution failed" in feedback


# =============================================================================
# 4. Auditor self-loop on too few cases (P5.1 검증, 통합)
# =============================================================================


def test_auditor_too_few_cases_self_loop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """auditor가 5개만 반환 → ``last_failed_node='auditor'`` self-loop."""
    only_5 = VALID_ADV_8[:5]
    _patch_chat(
        monkeypatch, "ipe.nodes.auditor.get_chat", _adv_response(only_5)
    )

    tracker = _make_tracker(tmp_path)
    state = _problem_state_with_solution()
    state = auditor.run(state, tracker=tracker)

    assert state["last_failed_node"] == "auditor"
    feedback = state.get("feedback_message") or ""
    # "only 5 valid cases, need >= 8" 등의 메시지 기대
    assert "5 valid cases" in feedback or "need >= 8" in feedback
