"""R14 PR 2 통합 테스트 — Coder fanout + Executor best 선택.

Coder가 fanout=N으로 N candidate를 만들고, Executor가 sample 검증으로
fail count 최소 candidate를 best로 선택하는지 검증. LLM은 mock으로 N개
다른 응답을 ``side_effect``로 주입.

전략:
- A+B problem, sample 2개 ("1 2"→"3", "10 20"→"30")
- 3 candidate:
  - cand_0: a*b (wrong — sample 2개 모두 fail)
  - cand_1: a-b (wrong — sample 2개 모두 fail)
  - cand_2: a+b (correct — sample 2개 모두 pass)
- 기대: Executor가 cand_2를 best로 선택 → Phase A 통과 → auditor 라우팅
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.nodes import coder, executor
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.state import ProblemState


def _make_resp(content: str) -> MagicMock:
    """ChatAnthropic invoke 반환값 mock — content + usage_metadata."""
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": 0, "output_tokens": 0}
    return resp


def _make_chat_with_responses(responses: list[str]) -> MagicMock:
    """N개 LLM 응답을 차례로 반환하는 mock chat. fanout=N 시나리오용."""
    chat = MagicMock()
    chat.model = "claude-sonnet-4-6"
    chat.temperature = 0.7
    chat.invoke.side_effect = [_make_resp(r) for r in responses]
    return chat


def _patch_coder_chat_with_responses(
    monkeypatch: pytest.MonkeyPatch, responses: list[str],
) -> MagicMock:
    """coder.get_chat을 mock — 매번 같은 chat 반환 (responses side_effect 공유)."""
    chat = _make_chat_with_responses(responses)
    monkeypatch.setattr("ipe.nodes.coder.get_chat", lambda *a, **k: chat)
    return chat


# 3 candidate 응답 — LESSON + 단일 fence (brute 없음, 본 테스트 focus는 best 선택만)
RESP_WRONG_MUL = (
    "LESSON: trying multiplication.\n"
    "```python\na, b = map(int, input().split())\nprint(a * b)\n```\n"
)
RESP_WRONG_SUB = (
    "LESSON: trying subtraction.\n"
    "```python\na, b = map(int, input().split())\nprint(a - b)\n```\n"
)
RESP_CORRECT_ADD = (
    "LESSON: correct addition.\n"
    "```python\na, b = map(int, input().split())\nprint(a + b)\n```\n"
)


def _state_for_a_plus_b(fanout: int) -> ProblemState:
    return {
        "target_algorithm": "A+B",
        "target_language": "python",
        "problem_description": "두 수 A와 B를 입력받아 A+B를 출력하라.",
        "constraints": "1 <= A, B <= 1e9",
        "sample_testcases": [
            {"input": "1 2\n", "expected_output": "3"},
            {"input": "10 20\n", "expected_output": "30"},
        ],
        "coder_fanout": fanout,
    }


def test_fanout_3_picks_correct_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """R14 PR 2: 3 candidate 중 a+b가 sample 통과 → Executor가 a+b 선택."""
    _patch_coder_chat_with_responses(
        monkeypatch,
        [RESP_WRONG_MUL, RESP_WRONG_SUB, RESP_CORRECT_ADD],
    )
    tracker = LLMCallTracker("test-fanout-3", tmp_path / "traces")

    state = _state_for_a_plus_b(fanout=3)

    # Coder — 3 candidate 생성
    state = coder.run(state, tracker=tracker)
    candidates = state.get("candidate_solutions") or []
    assert len(candidates) == 3
    # 첫 candidate는 wrong (a*b) — coder.run 단계에선 best 미선택
    assert "a * b" in state["solution_code"]

    # Executor — best 선택 → a+b 채택 → Phase A 통과 → auditor 라우팅
    state = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd",
    )
    assert state.get("final_status") is None
    assert state["last_failed_node"] == "auditor"  # Phase A pass + adversarial 부재
    # solution_code가 best로 교체됨 — a+b
    assert "a + b" in state["solution_code"]
    # Phase A 결과 — 2 sample 모두 pass
    results = state["execution_results"]
    samples_only = [r for r in results if r["phase"] == "sample"]
    assert len(samples_only) == 2
    assert all(r["pass"] for r in samples_only)


def test_fanout_1_skips_best_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """R14 PR 2: fanout=1은 best 선택 path 안 탐 — 기존 동작 유지 (회귀 0)."""
    _patch_coder_chat_with_responses(monkeypatch, [RESP_CORRECT_ADD])
    tracker = LLMCallTracker("test-fanout-1", tmp_path / "traces")

    state = _state_for_a_plus_b(fanout=1)
    state = coder.run(state, tracker=tracker)
    candidates = state.get("candidate_solutions") or []
    assert len(candidates) == 1  # fanout=1 시 candidate 1개만
    assert "a + b" in state["solution_code"]

    state = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd",
    )
    # 기존 path와 동일 — Phase A 통과 → auditor
    assert state["last_failed_node"] == "auditor"
