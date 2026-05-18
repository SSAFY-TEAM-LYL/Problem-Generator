"""Unit tests for ipe.observability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from ipe.observability import (
    PRICING,
    LLMCallTracker,
    ReplayTracker,
    _cost_usd,
    _invoke_with_retry,
    _is_retryable,
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


# =============================================================================
# ReplayTracker (P-2 / C2 / F3) — _load_traces edge cases + invoke
# =============================================================================


def _write_trace(
    traces_dir: Path,
    *,
    seq: int,
    node: str,
    response: str = "cached response",
    in_tok: int = 100,
    out_tok: int = 50,
    cost_usd: float = 0.005,
) -> None:
    """LLMCallTracker schema의 trace 파일을 직접 작성 (테스트 fixture)."""
    traces_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "seq": seq,
        "node": node,
        "model": "claude-opus-4-7",
        "messages": [{"role": "user", "content": "x"}],
        "response": response,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": cost_usd,
        "timestamp": "2026-05-09T12:00:00+00:00",
    }
    (traces_dir / f"{seq:04d}_{node}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


class TestReplayTrackerLoadTraces:
    def test_empty_dir_returns_empty_cache(self, tmp_path: Path) -> None:
        traces = tmp_path / "traces"
        traces.mkdir()
        tracker = ReplayTracker("run", traces)
        assert tracker._cache == {}

    def test_missing_dir_returns_empty_cache(self, tmp_path: Path) -> None:
        """LLMCallTracker.__init__ 가 mkdir(exist_ok=True) 하므로 dir 자동 생성되어
        cache는 빈 dict."""
        missing = tmp_path / "no_such"
        tracker = ReplayTracker("run", missing)
        assert tracker._cache == {}
        # subclass __init__이 mkdir하므로 dir이 생성되었어야
        assert missing.exists()

    def test_loads_valid_traces(self, tmp_path: Path) -> None:
        traces = tmp_path / "traces"
        _write_trace(traces, seq=1, node="architect")
        _write_trace(traces, seq=2, node="coder", response="def f(): pass")

        tracker = ReplayTracker("run", traces)
        assert set(tracker._cache.keys()) == {1, 2}
        assert tracker._cache[1]["node"] == "architect"
        assert tracker._cache[2]["response"] == "def f(): pass"

    def test_skips_non_int_prefix(self, tmp_path: Path) -> None:
        """파일명 prefix가 int가 아니면 ValueError 분기 — skip."""
        traces = tmp_path / "traces"
        _write_trace(traces, seq=1, node="ok")
        traces.mkdir(exist_ok=True)
        # 잘못된 파일명 (non-int prefix) — _load_traces가 skip
        (traces / "abc_node.json").write_text("{}", encoding="utf-8")

        tracker = ReplayTracker("run", traces)
        # 정상 파일만 로드
        assert tracker._cache == {1: tracker._cache[1]}
        assert "abc" not in str(tracker._cache.keys())

    def test_skips_malformed_json(self, tmp_path: Path) -> None:
        """JSON 파싱 실패 시 JSONDecodeError 분기 — skip."""
        traces = tmp_path / "traces"
        _write_trace(traces, seq=1, node="good")
        traces.mkdir(exist_ok=True)
        (traces / "0002_bad.json").write_text("{ not valid json", encoding="utf-8")

        tracker = ReplayTracker("run", traces)
        assert set(tracker._cache.keys()) == {1}
        assert 2 not in tracker._cache


class TestReplayTrackerInvoke:
    def test_returns_cached_aimessage(self, tmp_path: Path) -> None:
        traces = tmp_path / "traces"
        _write_trace(traces, seq=1, node="architect", response="cached!")

        tracker = ReplayTracker("run", traces)
        chat = MagicMock()  # invoke가 호출되면 안 됨 (replay)
        chat.invoke.side_effect = AssertionError("must not be called")
        state_calls: list[LLMCallRecord] = []

        resp = tracker.invoke(chat, [], node="architect", state_calls=state_calls)

        # AIMessage로 wrap 반환
        assert isinstance(resp, AIMessage)
        assert resp.content == "cached!"
        # chat.invoke는 호출 안 됨 (replay 핵심)
        chat.invoke.assert_not_called()

    def test_preserves_cached_cost_and_tokens(self, tmp_path: Path) -> None:
        """cache의 cost_usd / tokens가 state_calls record에 보존."""
        traces = tmp_path / "traces"
        _write_trace(traces, seq=1, node="coder", in_tok=200, out_tok=80, cost_usd=0.0123)

        tracker = ReplayTracker("run", traces)
        state_calls: list[LLMCallRecord] = []
        tracker.invoke(MagicMock(), [], node="coder", state_calls=state_calls)

        assert len(state_calls) == 1
        rec = state_calls[0]
        assert rec["seq"] == 1
        assert rec["node"] == "coder"
        assert rec["input_tokens"] == 200
        assert rec["output_tokens"] == 80
        assert rec["cost_usd"] == pytest.approx(0.0123)

    def test_cache_miss_raises_runtime_error(self, tmp_path: Path) -> None:
        """seq가 cache에 없으면 즉시 RuntimeError."""
        traces = tmp_path / "traces"
        traces.mkdir()  # 빈 디렉토리

        tracker = ReplayTracker("run", traces)
        with pytest.raises(RuntimeError, match="replay miss"):
            tracker.invoke(MagicMock(), [], node="architect", state_calls=[])

    def test_seq_increments_across_calls(self, tmp_path: Path) -> None:
        traces = tmp_path / "traces"
        _write_trace(traces, seq=1, node="a")
        _write_trace(traces, seq=2, node="b")

        tracker = ReplayTracker("run", traces)
        calls: list[LLMCallRecord] = []
        tracker.invoke(MagicMock(), [], node="a", state_calls=calls)
        tracker.invoke(MagicMock(), [], node="b", state_calls=calls)

        assert [c["seq"] for c in calls] == [1, 2]
        assert [c["node"] for c in calls] == ["a", "b"]


# =============================================================================
# R12 (Round 14) — Anthropic 일시 장애 retry helpers
# =============================================================================


def _api_status_error(status_code: int) -> Exception:
    """anthropic APIStatusError instance with given HTTP status (for test simulation)."""
    from anthropic import APIStatusError
    resp = MagicMock(status_code=status_code)
    return APIStatusError(message=f"http {status_code}", response=resp, body=None)


def _rate_limit_error() -> Exception:
    from anthropic import RateLimitError
    resp = MagicMock(status_code=429)
    return RateLimitError(message="rate limited", response=resp, body=None)


class TestIsRetryable:
    """HTTP status code 기반 + isinstance fallback으로 retryable 판별."""

    def test_rate_limit_error_is_retryable(self) -> None:
        assert _is_retryable(_rate_limit_error()) is True

    def test_overloaded_status_529_is_retryable(self) -> None:
        """anthropic 529 Overloaded — Round 12 BFS crash 원인."""
        assert _is_retryable(_api_status_error(529)) is True

    def test_server_5xx_is_retryable(self) -> None:
        for status in (500, 502, 503, 504):
            assert _is_retryable(_api_status_error(status)) is True, f"status {status}"

    def test_request_timeout_408_is_retryable(self) -> None:
        assert _is_retryable(_api_status_error(408)) is True

    def test_client_4xx_not_retryable(self) -> None:
        """400/401/403/404 같은 client error는 retry 금지 (사용자 잘못)."""
        for status in (400, 401, 403, 404):
            assert _is_retryable(_api_status_error(status)) is False, f"status {status}"

    def test_arbitrary_exception_not_retryable(self) -> None:
        assert _is_retryable(ValueError("bug")) is False
        assert _is_retryable(RuntimeError("oops")) is False


class TestInvokeWithRetry:
    """exponential backoff retry — 2 → 4 → 8 secs, max 3 retries."""

    def _mock_chat(self, side_effect: list[Any]) -> MagicMock:
        chat = MagicMock()
        chat.invoke.side_effect = side_effect
        return chat

    def test_first_attempt_success_no_sleep(self) -> None:
        resp = MagicMock(spec=BaseMessage)
        chat = self._mock_chat([resp])
        sleeps: list[float] = []
        result = _invoke_with_retry(chat, [], sleep=sleeps.append)
        assert result is resp
        assert chat.invoke.call_count == 1
        assert sleeps == []

    def test_retry_after_overloaded_then_success(self) -> None:
        resp = MagicMock(spec=BaseMessage)
        chat = self._mock_chat([_api_status_error(529), resp])
        sleeps: list[float] = []
        result = _invoke_with_retry(chat, [], base_backoff=2.0, sleep=sleeps.append)
        assert result is resp
        assert chat.invoke.call_count == 2
        assert sleeps == [2.0]  # first backoff = 2.0 * 2^0

    def test_two_retries_then_success_exponential_backoff(self) -> None:
        resp = MagicMock(spec=BaseMessage)
        chat = self._mock_chat([_rate_limit_error(), _api_status_error(503), resp])
        sleeps: list[float] = []
        result = _invoke_with_retry(chat, [], base_backoff=2.0, sleep=sleeps.append)
        assert result is resp
        assert chat.invoke.call_count == 3
        assert sleeps == [2.0, 4.0]  # exponential: 2*2^0, 2*2^1

    def test_all_retries_exhausted_raises_last(self) -> None:
        errs = [_api_status_error(529) for _ in range(4)]  # 4 attempts (1 + 3 retries)
        chat = self._mock_chat(errs)
        sleeps: list[float] = []
        from anthropic import APIStatusError
        with pytest.raises(APIStatusError) as excinfo:
            _invoke_with_retry(chat, [], max_retries=3, base_backoff=2.0, sleep=sleeps.append)
        assert excinfo.value.status_code == 529
        assert chat.invoke.call_count == 4  # initial + 3 retries
        assert sleeps == [2.0, 4.0, 8.0]  # 3 backoffs before final failure

    def test_non_retryable_raised_immediately(self) -> None:
        """RateLimit/Overloaded 아닌 예외는 retry 없이 즉시 raise."""
        chat = self._mock_chat([_api_status_error(400)])
        sleeps: list[float] = []
        from anthropic import APIStatusError
        with pytest.raises(APIStatusError) as excinfo:
            _invoke_with_retry(chat, [], sleep=sleeps.append)
        assert excinfo.value.status_code == 400
        assert chat.invoke.call_count == 1
        assert sleeps == []

    def test_arbitrary_exception_raised_immediately(self) -> None:
        chat = self._mock_chat([ValueError("bug")])
        sleeps: list[float] = []
        with pytest.raises(ValueError):
            _invoke_with_retry(chat, [], sleep=sleeps.append)
        assert chat.invoke.call_count == 1
        assert sleeps == []


class TestLLMCallTrackerUsesRetry:
    """tracker.invoke가 _invoke_with_retry를 사용 — Anthropic 일시 장애에 자동 복구."""

    def test_tracker_invoke_retries_on_overloaded(self, tmp_path: Path) -> None:
        """tracker가 Overloaded 1회 후 자동 retry로 success — Round 12 BFS crash 시나리오."""
        chat = MagicMock()
        chat.model = "claude-opus-4-7"
        resp = MagicMock(spec=BaseMessage)
        resp.content = "after retry"
        resp.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
        chat.invoke.side_effect = [_api_status_error(529), resp]

        tracker = LLMCallTracker("test-r12", tmp_path / "traces")
        state_calls: list[LLMCallRecord] = []

        # sleep을 mock하여 테스트 빠르게 (실제 backoff 2초 대기 안 함)
        import ipe.observability as obs
        original_sleep = obs.time.sleep
        obs.time.sleep = lambda _: None
        try:
            result = tracker.invoke(chat, [], node="architect", state_calls=state_calls)
        finally:
            obs.time.sleep = original_sleep

        assert result is resp
        assert chat.invoke.call_count == 2
        assert len(state_calls) == 1
        assert state_calls[0]["input_tokens"] == 10
