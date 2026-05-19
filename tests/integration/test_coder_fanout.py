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


# =============================================================================
# R-coder-parse (Round 18) — fenced block 누락 graceful fallback
# =============================================================================


# fenced block 없는 응답 (LLM이 prose만 반환하는 패턴)
RESP_NO_FENCE = "I think the answer is simply: a + b. No code block."
RESP_NO_FENCE_2 = "Just print a+b directly without code formatting."


def test_coder_self_loops_when_all_candidates_lack_fence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """R-coder-parse: fanout=2, 둘 다 fenced block 없음 → ValueError 대신 self-loop."""
    _patch_coder_chat_with_responses(monkeypatch, [RESP_NO_FENCE, RESP_NO_FENCE_2])

    tracker = LLMCallTracker("test", tmp_path / "traces")
    state = _state_for_a_plus_b(fanout=2)
    state["llm_calls"] = []
    state["target_language"] = "python"

    # crash 없이 정상 return
    out = coder.run(state, tracker=tracker)

    assert out.get("last_failed_node") == "coder", "self-loop으로 라우팅"
    fb = out.get("feedback_message") or ""
    assert "Coder response parse failed" in fb
    assert "fenced block" in fb
    # solution_code는 set되지 않음 (실패)
    assert "solution_code" not in out or not out.get("solution_code")


def test_coder_proceeds_when_one_candidate_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """fanout=3, 1개만 valid → 그 candidate로 진행 (graceful continue)."""
    _patch_coder_chat_with_responses(
        monkeypatch,
        [RESP_NO_FENCE, RESP_CORRECT_ADD, RESP_NO_FENCE_2],
    )

    tracker = LLMCallTracker("test", tmp_path / "traces")
    state = _state_for_a_plus_b(fanout=3)
    state["llm_calls"] = []
    state["target_language"] = "python"

    out = coder.run(state, tracker=tracker)

    # 1개 valid candidate가 채택됨 → 정상 진행
    assert out.get("last_failed_node") is None, "정상 진행 (self-loop 아님)"
    assert "print(a + b)" in (out.get("solution_code") or ""), "valid candidate 채택"
    assert (out.get("candidate_solutions") or []) != [], "candidates 비어있지 않음"
    # 1개 candidate만 (2개는 parse fail로 제외됨)
    assert len(out["candidate_solutions"]) == 1
