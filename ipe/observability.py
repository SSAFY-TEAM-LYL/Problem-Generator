"""LLM 호출 회계, 메트릭, 로깅.

스펙: ARCHITECTURE.md §3.12 (ipe/observability.py)

- PRICING: model API ID → 단가 (USD per 1M tokens) SSOT
- _cost_usd: 토큰 수 → USD 비용
- LLMCallTracker: chat.invoke wrap — state["llm_calls"] 누적 + raw trace 저장
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage

from ipe.state import LLMCallRecord

# ============================================================================
# 모델별 단가 (USD per 1M tokens) — 2026-05 기준
# 모델 추가 시: ARCH §3.3.0 매핑 표와 동기화 필요.
# ============================================================================

PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-7":           {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6":         {"input":  3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input":  1.0, "output":  5.0},
}


def _cost_usd(model: str, in_tokens: int, out_tokens: int) -> float:
    """입출력 토큰 수를 USD 비용으로 변환. 모르는 model은 0.0."""
    p = PRICING.get(model)
    if not p:
        return 0.0
    return (in_tokens * p["input"] + out_tokens * p["output"]) / 1_000_000


def _serialize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """messages를 JSON-serializable dict list로 변환.

    - dict: 그대로
    - BaseMessage: ``{"role": <type>, "content": <stringified>}``
    - 기타: ``{"role": "unknown", "content": str(...)}``
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, dict):
            out.append(m)
        elif isinstance(m, BaseMessage):
            out.append({"role": m.type, "content": str(m.content)})
        else:
            out.append({"role": "unknown", "content": str(m)})
    return out


class LLMCallTracker:
    """LLM 호출에 자동으로 토큰·비용·trace를 부착하는 thin wrapper.

    Usage::

        tracker = LLMCallTracker(run_id, outputs_dir / "llm_traces")
        resp = tracker.invoke(
            chat, messages, node="architect", state_calls=state["llm_calls"],
        )
    """

    def __init__(self, run_id: str, traces_dir: Path) -> None:
        self.run_id = run_id
        self.traces_dir = traces_dir
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        self.seq = 0

    def invoke(
        self,
        chat: ChatAnthropic,
        messages: list[Any],
        *,
        node: str,
        state_calls: list[LLMCallRecord],
    ) -> BaseMessage:
        """``chat.invoke``를 wrap — 응답 반환 + 토큰/비용 계산 + trace 저장."""
        self.seq += 1
        seq = self.seq
        ts = datetime.now(UTC).isoformat()

        resp = chat.invoke(messages)

        usage = getattr(resp, "usage_metadata", None) or {}
        in_tok = int(usage.get("input_tokens", 0))
        out_tok = int(usage.get("output_tokens", 0))
        model = str(getattr(chat, "model", "unknown"))
        cost = _cost_usd(model, in_tok, out_tok)

        # raw trace 저장
        trace_path = self.traces_dir / f"{seq:04d}_{node}.json"
        trace_data: dict[str, Any] = {
            "seq": seq,
            "node": node,
            "model": model,
            "messages": _serialize_messages(messages),
            "response": str(resp.content) if isinstance(resp, BaseMessage) else str(resp),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": cost,
            "timestamp": ts,
        }
        trace_path.write_text(
            json.dumps(trace_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # state["llm_calls"]에 record 추가
        # trace_path는 환경 독립적 상대경로로 저장 (B4 fix, 2026-05-08).
        # 형식: "<traces_dir.name>/<seq>_<node>.json" (예: "llm_traces/0001_architect.json")
        # 운영에서는 outputs/<run_id>/llm_traces/ 가 traces_dir이므로
        # outputs root 기준의 의미 있는 상대 경로가 된다.
        record: LLMCallRecord = {
            "seq": seq,
            "node": node,
            "model": model,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": cost,
            "timestamp": ts,
            "trace_path": f"{self.traces_dir.name}/{trace_path.name}",
        }
        state_calls.append(record)

        if not isinstance(resp, BaseMessage):
            raise TypeError(f"unexpected response type from chat.invoke: {type(resp).__name__}")
        return resp
