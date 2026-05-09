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
from langchain_core.messages import AIMessage, BaseMessage

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


class ReplayTracker(LLMCallTracker):
    """LLMCallTracker drop-in replacement — chat.invoke 우회 + cached trace 응답 (P8.3).

    ``--replay <run_id>`` 모드에서 사용. seq 순서대로 ``traces_dir`` 의 JSON 파일을
    읽어 ``AIMessage`` 로 wrap하여 반환. LLM 호출 0회 (비용 0) — 디버깅 + 재현용.

    seq 매칭은 super-step 순서가 결정론적이라는 가정에 의존:
    architect(seq=1) → coder(seq=2) → auditor(seq=3) → generator(seq=4) → ...
    같은 입력으로 graph.invoke를 다시 돌리면 같은 순서로 호출 → 같은 trace 응답.
    """

    def __init__(self, run_id: str, traces_dir: Path) -> None:
        super().__init__(run_id, traces_dir)
        self._cache: dict[int, dict[str, Any]] = self._load_traces(traces_dir)

    @staticmethod
    def _load_traces(traces_dir: Path) -> dict[int, dict[str, Any]]:
        """``traces_dir`` 안의 ``<seq:04d>_<node>.json`` 파일들을 seq → dict로 로드."""
        cache: dict[int, dict[str, Any]] = {}
        if not traces_dir.exists():
            return cache
        for p in sorted(traces_dir.glob("*.json")):
            try:
                seq = int(p.stem.split("_", 1)[0])
            except ValueError:
                continue
            try:
                cache[seq] = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
        return cache

    def invoke(
        self,
        chat: ChatAnthropic,
        messages: list[Any],
        *,
        node: str,
        state_calls: list[LLMCallRecord],
    ) -> BaseMessage:
        """chat.invoke를 우회 — cached trace의 response를 AIMessage로 반환."""
        self.seq += 1
        seq = self.seq
        cached = self._cache.get(seq)
        if cached is None:
            raise RuntimeError(
                f"replay miss: seq={seq} node={node} not found in {self.traces_dir}"
            )

        cached_node = str(cached.get("node", node))
        record: LLMCallRecord = {
            "seq": seq,
            "node": cached_node,
            "model": str(cached.get("model", "unknown")),
            "input_tokens": int(cached.get("input_tokens", 0)),
            "output_tokens": int(cached.get("output_tokens", 0)),
            "cost_usd": float(cached.get("cost_usd", 0.0)),
            "timestamp": str(cached.get("timestamp", "")),
            "trace_path": f"{self.traces_dir.name}/{seq:04d}_{cached_node}.json",
        }
        state_calls.append(record)
        return AIMessage(content=str(cached.get("response", "")))
