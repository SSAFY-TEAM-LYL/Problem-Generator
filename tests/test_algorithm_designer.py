"""algorithm_designer.py 단위 테스트 — M1 (v0.3.0 RFC §M1).

LLM mock + parse path 검증. 통합 흐름 (graph 통해 호출)은 integration test에서.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.nodes.algorithm_designer import _format_samples, _route_back, run
from ipe.observability import LLMCallTracker
from ipe.state import LLMCallRecord, ProblemState


def _make_chat_returning(content: str) -> MagicMock:
    chat = MagicMock()
    chat.model = "claude-sonnet-4-6"
    chat.temperature = 0.3
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": 10, "output_tokens": 20}
    chat.invoke.return_value = resp
    return chat


VALID_DESIGN_JSON = """```json
{
  "name": "BFS shortest path",
  "pseudocode": "1. queue = [start]\\n2. dist[start] = 0\\n3. while queue ...",
  "complexity_target": "Time O(V+E), Space O(V)",
  "edge_cases": ["disconnected graph", "single node", "self-loop"]
}
```"""


class TestFormatSamples:
    def test_empty_returns_placeholder(self) -> None:
        assert _format_samples([]) == "(no samples)"

    def test_single_sample_formatted(self) -> None:
        out = _format_samples([{"input": "1 2", "expected_output": "3"}])
        assert "Sample 1" in out
        assert "1 2" in out
        assert "3" in out

    def test_caps_at_5_samples(self) -> None:
        """6개 sample이 있어도 5개만 prompt에 포함 (cost 절약)."""
        samples = [{"input": str(i), "expected_output": str(i)} for i in range(6)]
        out = _format_samples(samples)
        assert "Sample 5" in out
        assert "Sample 6" not in out

    def test_truncates_long_input(self) -> None:
        big = "x" * 500
        out = _format_samples([{"input": big, "expected_output": "ok"}])
        assert "x" * 200 in out
        assert "x" * 300 not in out


class TestRouteBack:
    def test_sets_failed_node_and_feedback(self) -> None:
        state: ProblemState = {"target_algorithm": "BFS"}
        calls: list[LLMCallRecord] = []
        out = _route_back(state, calls, "test reason")
        assert out["last_failed_node"] == "algorithm_designer"
        assert out["feedback_message"] == "test reason"
        assert out["target_algorithm"] == "BFS"


class TestRun:
    def _setup(self, tmp_path: Path, response: str) -> tuple[LLMCallTracker, MagicMock]:
        tracker = LLMCallTracker("test", tmp_path / "traces")
        chat = _make_chat_returning(response)
        return tracker, chat

    def _state(self) -> ProblemState:
        return {
            "problem_description": "Find shortest path in unweighted graph",
            "constraints": "1 <= V <= 100000, 1 <= E <= 200000",
            "sample_testcases": [{"input": "3 2\n1 2\n2 3", "expected_output": "2"}],
            "llm_calls": [],
        }

    def test_valid_response_sets_algorithm_design(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tracker, chat = self._setup(tmp_path, VALID_DESIGN_JSON)
        monkeypatch.setattr("ipe.nodes.algorithm_designer.get_chat",
                            lambda *a, **k: chat)

        out = run(self._state(), tracker=tracker)

        assert out.get("last_failed_node") is None
        design = out.get("algorithm_design")
        assert design is not None
        assert design["name"] == "BFS shortest path"
        assert "queue" in design["pseudocode"]
        assert "O(V+E)" in design["complexity_target"]
        assert len(design["edge_cases"]) == 3
        assert "disconnected graph" in design["edge_cases"]

    def test_invalid_json_routes_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tracker, chat = self._setup(tmp_path, "not valid json at all")
        monkeypatch.setattr("ipe.nodes.algorithm_designer.get_chat",
                            lambda *a, **k: chat)

        out = run(self._state(), tracker=tracker)

        assert out.get("last_failed_node") == "algorithm_designer"
        assert "JSON parse error" in (out.get("feedback_message") or "")

    def test_non_dict_response_routes_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tracker, chat = self._setup(tmp_path, '```json\n["just", "a", "list"]\n```')
        monkeypatch.setattr("ipe.nodes.algorithm_designer.get_chat",
                            lambda *a, **k: chat)

        out = run(self._state(), tracker=tracker)

        assert out.get("last_failed_node") == "algorithm_designer"
        assert "not a JSON object" in (out.get("feedback_message") or "")

    def test_missing_field_routes_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        partial = """```json
{"name": "BFS", "edge_cases": []}
```"""
        tracker, chat = self._setup(tmp_path, partial)
        monkeypatch.setattr("ipe.nodes.algorithm_designer.get_chat",
                            lambda *a, **k: chat)

        out = run(self._state(), tracker=tracker)

        assert out.get("last_failed_node") == "algorithm_designer"
        fb = out.get("feedback_message") or ""
        assert "missing fields" in fb
        assert "pseudocode" in fb
        assert "complexity_target" in fb

    def test_edge_cases_not_list_routes_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad = """```json
{"name": "BFS", "pseudocode": "...", "complexity_target": "O(N)", "edge_cases": "not a list"}
```"""
        tracker, chat = self._setup(tmp_path, bad)
        monkeypatch.setattr("ipe.nodes.algorithm_designer.get_chat",
                            lambda *a, **k: chat)

        out = run(self._state(), tracker=tracker)

        assert out.get("last_failed_node") == "algorithm_designer"
        assert "edge_cases must be a list" in (out.get("feedback_message") or "")

    def test_clears_previous_feedback_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tracker, chat = self._setup(tmp_path, VALID_DESIGN_JSON)
        monkeypatch.setattr("ipe.nodes.algorithm_designer.get_chat",
                            lambda *a, **k: chat)

        state = self._state()
        state["feedback_message"] = "previous error"
        state["last_failed_node"] = "algorithm_designer"
        out = run(state, tracker=tracker)

        assert out.get("feedback_message") is None
        assert out.get("last_failed_node") is None
