"""reviewer.py 단위 테스트 — M4 (v0.3.0 RFC §M4).

LLM mock + verdict 경로 검증. 통합 흐름 (graph 통해 호출)은 integration test에서.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.nodes.reviewer import (
    _approve,
    _format_design,
    _format_samples,
    _reject,
    run,
)
from ipe.observability import LLMCallTracker
from ipe.state import LLMCallRecord, ProblemState


def _make_chat(content: str) -> MagicMock:
    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    chat.temperature = None
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": 0, "output_tokens": 0}
    chat.invoke.return_value = resp
    return chat


def _make_tracker(tmp_path: Path) -> LLMCallTracker:
    return LLMCallTracker("test-run", tmp_path / "traces")


def _state_with_solution(code: str = "print(0)") -> ProblemState:
    return {
        "problem_description": "Sum two integers.",
        "constraints": "1 <= a, b <= 1e9",
        "target_language": "python",
        "sample_testcases": [
            {"input": "1 2\n", "expected_output": "3"},
            {"input": "5 7\n", "expected_output": "12"},
        ],
        "solution_code": code,
        "llm_calls": [],
    }


APPROVE_JSON = """```json
{"verdict": "approve", "reasoning": "Looks correct.", "weaknesses": []}
```"""

REJECT_JSON = """```json
{
  "verdict": "reject",
  "reasoning": "Wrong algorithm.",
  "weaknesses": ["fails on N=1", "no buffered IO"]
}
```"""


# =============================================================================
# _format_samples — sample block 빌더
# =============================================================================


class TestFormatSamples:
    def test_empty(self) -> None:
        assert _format_samples([]) == "(no samples)"

    def test_single(self) -> None:
        out = _format_samples([{"input": "1 2", "expected_output": "3"}])
        assert "Sample 1" in out
        assert "1 2" in out
        assert "3" in out

    def test_caps_at_5(self) -> None:
        samples = [{"input": str(i), "expected_output": str(i)} for i in range(7)]
        out = _format_samples(samples)
        assert "Sample 5" in out
        assert "Sample 6" not in out


# =============================================================================
# _format_design — algorithm_design block 빌더
# =============================================================================


class TestFormatDesign:
    def test_none_design_returns_placeholder(self) -> None:
        out = _format_design(None)
        assert "no design" in out

    def test_with_design(self) -> None:
        design: dict[str, Any] = {
            "name": "BFS",
            "complexity_target": "O(V+E)",
            "pseudocode": "1. init queue\n2. ...",
            "edge_cases": ["disconnected", "single node"],
        }
        out = _format_design(design)
        assert "BFS" in out
        assert "O(V+E)" in out
        assert "disconnected" in out

    def test_design_without_edge_cases(self) -> None:
        design: dict[str, Any] = {
            "name": "X",
            "complexity_target": "O(N)",
            "pseudocode": "1. ...",
            "edge_cases": [],
        }
        out = _format_design(design)
        assert "none specified" in out


# =============================================================================
# _approve / _reject — state 빌더
# =============================================================================


class TestApproveReject:
    def test_approve_clears_failed_signals(self) -> None:
        calls: list[LLMCallRecord] = []
        state: ProblemState = {
            "feedback_message": "previous",
            "last_failed_node": "coder",
        }
        out = _approve(state, calls, "ok")
        assert out["review_status"] == "approved"
        assert out["review_reasoning"] == "ok"
        assert out["review_weaknesses"] == []
        assert out.get("feedback_message") is None
        assert out.get("last_failed_node") is None

    def test_reject_routes_back_to_coder(self) -> None:
        calls: list[LLMCallRecord] = []
        state: ProblemState = {}
        out = _reject(state, calls, "wrong", ["case A", "case B"])
        assert out["review_status"] == "rejected"
        assert out["review_reasoning"] == "wrong"
        assert out["review_weaknesses"] == ["case A", "case B"]
        assert out["last_failed_node"] == "coder"
        fb = out.get("feedback_message") or ""
        assert "Reviewer rejected" in fb
        assert "case A" in fb
        assert "case B" in fb


# =============================================================================
# run — verdict 경로 5종
# =============================================================================


class TestRun:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, response: str) -> None:
        monkeypatch.setattr(
            "ipe.nodes.reviewer.get_chat", lambda *a, **k: _make_chat(response)
        )

    def test_approve_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._setup(monkeypatch, APPROVE_JSON)
        out = run(_state_with_solution(), tracker=_make_tracker(tmp_path))
        assert out["review_status"] == "approved"
        assert "correct" in (out.get("review_reasoning") or "").lower()
        assert out.get("last_failed_node") is None

    def test_reject_path_routes_to_coder(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._setup(monkeypatch, REJECT_JSON)
        out = run(_state_with_solution(), tracker=_make_tracker(tmp_path))
        assert out["review_status"] == "rejected"
        assert out["last_failed_node"] == "coder"
        assert "fails on N=1" in (out.get("feedback_message") or "")
        assert len(out.get("review_weaknesses") or []) == 2

    def test_missing_solution_rejects_conservatively(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """solution_code 없으면 LLM call 없이 reject + coder retry."""
        # chat이 호출되면 안 됨 — stub은 raise로 fail-fast
        def must_not_call(*a: Any, **k: Any) -> Any:
            raise AssertionError("must not call get_chat when solution_code is empty")

        monkeypatch.setattr("ipe.nodes.reviewer.get_chat", must_not_call)
        state: ProblemState = {"problem_description": "X", "llm_calls": []}
        out = run(state, tracker=_make_tracker(tmp_path))
        assert out["review_status"] == "rejected"
        assert out["last_failed_node"] == "coder"
        assert "solution_code is empty" in (out.get("review_weaknesses") or [""])[0]

    def test_unparseable_response_graceful_approve(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """parse 실패 → graceful approve (executor가 검증). budget 보호."""
        self._setup(monkeypatch, "not valid json at all")
        out = run(_state_with_solution(), tracker=_make_tracker(tmp_path))
        assert out["review_status"] == "approved"
        assert "unparseable" in (out.get("review_reasoning") or "")

    def test_non_dict_response_graceful_approve(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._setup(monkeypatch, '```json\n[1, 2, 3]\n```')
        out = run(_state_with_solution(), tracker=_make_tracker(tmp_path))
        assert out["review_status"] == "approved"
        assert "not a JSON object" in (out.get("review_reasoning") or "")

    def test_unknown_verdict_graceful_approve(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """verdict가 approve/reject 외 값 → graceful approve."""
        self._setup(
            monkeypatch,
            '```json\n{"verdict": "maybe", "reasoning": "?", "weaknesses": []}\n```',
        )
        out = run(_state_with_solution(), tracker=_make_tracker(tmp_path))
        assert out["review_status"] == "approved"
        assert "unrecognized" in (out.get("review_reasoning") or "")

    def test_design_passed_to_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """algorithm_design이 state에 있으면 prompt에 포함됨."""
        captured: dict[str, Any] = {}

        def fake_get_chat(*a: Any, **k: Any) -> MagicMock:
            chat = _make_chat(APPROVE_JSON)
            orig_invoke = chat.invoke

            def capture(messages: Any) -> Any:
                captured["messages"] = messages
                return orig_invoke(messages)

            chat.invoke = capture
            return chat

        monkeypatch.setattr("ipe.nodes.reviewer.get_chat", fake_get_chat)
        state = _state_with_solution()
        state["algorithm_design"] = {
            "name": "Two Sum (hash)",
            "complexity_target": "O(N)",
            "pseudocode": "1. for each x ...",
            "edge_cases": ["empty array"],
        }
        run(state, tracker=_make_tracker(tmp_path))
        # user message에 algorithm_design이 포함됐어야
        user_content = captured["messages"][1]["content"]
        assert "Two Sum (hash)" in user_content
        assert "empty array" in user_content

    def test_records_one_llm_call(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._setup(monkeypatch, APPROVE_JSON)
        out = run(_state_with_solution(), tracker=_make_tracker(tmp_path))
        calls = out.get("llm_calls") or []
        assert len(calls) == 1
        assert calls[0].get("node") == "reviewer"
        assert calls[0].get("model") == "claude-opus-4-7"
