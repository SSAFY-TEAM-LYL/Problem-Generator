"""Unit tests for ipe.observability."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from ipe.observability import (
    PRICING,
    LLMCallTracker,
    _cost_usd,
    _serialize_messages,
)
from ipe.state import LLMCallRecord


class TestPricing:
    def test_required_models_present(self) -> None:
        assert "claude-opus-4-7" in PRICING
        assert "claude-sonnet-4-6" in PRICING
        assert "claude-haiku-4-5-20251001" in PRICING

    def test_opus_pricing_values(self) -> None:
        p = PRICING["claude-opus-4-7"]
        assert p["input"] == 15.0
        assert p["output"] == 75.0

    def test_output_more_expensive_than_input(self) -> None:
        for model, p in PRICING.items():
            assert p["output"] > p["input"], f"{model} output should cost more"


class TestCostUsd:
    def test_opus_calculation(self) -> None:
        # 1000 * 15 + 500 * 75 = 52500 / 1M = 0.0525
        cost = _cost_usd("claude-opus-4-7", 1000, 500)
        assert cost == pytest.approx(0.0525)

    def test_sonnet_calculation(self) -> None:
        # 1000 * 3 + 500 * 15 = 10500 / 1M = 0.0105
        cost = _cost_usd("claude-sonnet-4-6", 1000, 500)
        assert cost == pytest.approx(0.0105)

    def test_unknown_model_zero(self) -> None:
        assert _cost_usd("claude-fake", 1000, 500) == 0.0

    def test_zero_tokens(self) -> None:
        assert _cost_usd("claude-opus-4-7", 0, 0) == 0.0


class TestSerializeMessages:
    def test_dict_passthrough(self) -> None:
        msgs = [{"role": "user", "content": "hi"}]
        assert _serialize_messages(msgs) == msgs

    def test_base_message_human(self) -> None:
        result = _serialize_messages([HumanMessage(content="hi")])
        assert result[0]["role"] == "human"
        assert result[0]["content"] == "hi"

    def test_base_message_ai(self) -> None:
        result = _serialize_messages([AIMessage(content="hello")])
        assert result[0]["role"] == "ai"
        assert result[0]["content"] == "hello"

    def test_unknown_type(self) -> None:
        result = _serialize_messages([42])
        assert result[0]["role"] == "unknown"
        assert result[0]["content"] == "42"


def _make_mock_chat(model: str, in_tok: int, out_tok: int, content: str = "ok") -> MagicMock:
    """BaseMessage-spec mock response를 invoke하는 chat mock."""
    chat = MagicMock()
    chat.model = model
    mock_resp = MagicMock(spec=BaseMessage)
    mock_resp.content = content
    mock_resp.usage_metadata = {"input_tokens": in_tok, "output_tokens": out_tok}
    chat.invoke.return_value = mock_resp
    return chat


class TestLLMCallTracker:
    def test_invoke_records_state_and_writes_trace(self, tmp_path: Path) -> None:
        chat = _make_mock_chat("claude-opus-4-7", 100, 50, content="hello back")
        traces_dir = tmp_path / "traces"
        tracker = LLMCallTracker("test-run", traces_dir)
        state_calls: list[LLMCallRecord] = []

        messages = [{"role": "user", "content": "hi"}]
        resp = tracker.invoke(chat, messages, node="architect", state_calls=state_calls)

        # 응답 그대로 반환
        assert resp is chat.invoke.return_value

        # state_calls에 1건 누적
        assert len(state_calls) == 1
        rec = state_calls[0]
        assert rec["seq"] == 1
        assert rec["node"] == "architect"
        assert rec["model"] == "claude-opus-4-7"
        assert rec["input_tokens"] == 100
        assert rec["output_tokens"] == 50
        # 100*15 + 50*75 = 5250 / 1M = 0.00525
        assert rec["cost_usd"] == pytest.approx(0.00525)
        assert rec["timestamp"]  # ISO 8601 string
        # B4: trace_path는 traces_dir.name 기준 상대경로 (절대경로 X)
        assert rec["trace_path"] == "traces/0001_architect.json"
        assert not rec["trace_path"].startswith("/")  # 절대경로 거부

        # trace 파일 존재 + 내용 확인
        trace_files = list(traces_dir.iterdir())
        assert len(trace_files) == 1
        assert trace_files[0].name == "0001_architect.json"
        trace = json.loads(trace_files[0].read_text(encoding="utf-8"))
        assert trace["node"] == "architect"
        assert trace["model"] == "claude-opus-4-7"
        assert trace["response"] == "hello back"

    def test_seq_increments_across_calls(self, tmp_path: Path) -> None:
        chat = _make_mock_chat("claude-opus-4-7", 10, 5)
        tracker = LLMCallTracker("run-id", tmp_path / "traces")
        calls: list[LLMCallRecord] = []

        tracker.invoke(chat, [], node="a", state_calls=calls)
        tracker.invoke(chat, [], node="b", state_calls=calls)
        tracker.invoke(chat, [], node="a", state_calls=calls)

        assert [c["seq"] for c in calls] == [1, 2, 3]
        assert [c["node"] for c in calls] == ["a", "b", "a"]

        # trace 파일 3개 생성
        trace_files = sorted((tmp_path / "traces").iterdir())
        assert [f.name for f in trace_files] == [
            "0001_a.json",
            "0002_b.json",
            "0003_a.json",
        ]

    def test_missing_usage_metadata_defaults_to_zero(self, tmp_path: Path) -> None:
        chat = MagicMock()
        chat.model = "claude-opus-4-7"
        mock_resp = MagicMock(spec=BaseMessage)
        mock_resp.content = "x"
        mock_resp.usage_metadata = None  # 일부 응답엔 누락
        chat.invoke.return_value = mock_resp

        tracker = LLMCallTracker("run", tmp_path / "traces")
        calls: list[LLMCallRecord] = []
        tracker.invoke(chat, [], node="x", state_calls=calls)

        assert calls[0]["input_tokens"] == 0
        assert calls[0]["output_tokens"] == 0
        assert calls[0]["cost_usd"] == 0.0

    def test_unknown_response_type_raises(self, tmp_path: Path) -> None:
        chat = MagicMock()
        chat.model = "claude-opus-4-7"
        chat.invoke.return_value = "raw string, not BaseMessage"

        tracker = LLMCallTracker("run", tmp_path / "traces")
        with pytest.raises(TypeError, match="unexpected response type"):
            tracker.invoke(chat, [], node="x", state_calls=[])
