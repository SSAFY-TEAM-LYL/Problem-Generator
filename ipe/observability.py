"""LLM 호출 회계, 메트릭, 로깅.

스펙: ARCHITECTURE.md §3.12 (ipe/observability.py)

- PRICING: model API ID → 단가 (USD per 1M tokens) SSOT
- _cost_usd: 토큰 수 → USD 비용
- LLMCallTracker: chat.invoke wrap — state["llm_calls"] 누적 + raw trace 저장
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage

from ipe.state import LLMCallRecord

_metric_logger = logging.getLogger("ipe.observability")


def emit_metric(name: str, value: float | int, /, **labels: Any) -> None:
    """표준 메트릭 emitter (P11.2) — JsonFormatter가 JSON 라인으로 stdout emit.

    형식: ``logger.info("metric", extra={"metric": name, "value": value, **labels})``

    표준 메트릭 키:
    - ``ipe.node.latency_ms`` — LLM 호출 wall time (ms)
    - ``ipe.node.tokens_in`` / ``ipe.node.tokens_out`` — token 수
    - ``ipe.node.cost_usd`` — USD 비용
    - ``ipe.phase.exec_status`` — executor phase 결과 (예약, P12)

    labels 예: ``node="architect"``, ``model="claude-opus-4-7"``, ``seq=1``.
    """
    _metric_logger.info(
        "metric",
        extra={"metric": name, "value": value, **labels},
    )

# ============================================================================
# 모델별 단가 (USD per 1M tokens) — 2026-05 기준
# 모델 추가 시: ARCH §3.3.0 매핑 표와 동기화 필요.
#
# 주의 (R6 — 2026-05-10 v0.2.0 Sprint 1):
#   - **List price 기준** — Anthropic 공개 가격표 그대로.
#   - **Tier 할인 / 월 사용량 할인 미반영** — 본 측정값은 운영 계정의 실제
#     청구액보다 클 수 있음 (e2e Run 1+2 누적: 우리 $4.84 vs Anthropic $1.98,
#     ≈ 2.4× 과대 측정).
#   - **Prompt caching 미반영** — `cache_creation_input_tokens` /
#     `cache_read_input_tokens`가 LangChain ChatAnthropic의 `usage_metadata`
#     로 노출되면 보정 필요. 현재는 input/output만 사용.
#   - 따라서 ``cost_usd``는 **upper bound** (cost guard용으로는 안전 — 실제
#     보다 빨리 trigger됨). 정확한 청구액은 Anthropic console 참조.
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


# ============================================================================
# R12 (Round 14) — Anthropic 일시 장애 retry/backoff
#
# 배경: Round 12 BFS Docker run에서 `anthropic._exceptions.OverloadedError`
# (HTTP 529) 발생 시 즉시 crash. retry 없음. 운영 안정성 저해.
#
# 설계: HTTP status code 기반 판별 (+ isinstance fallback for network/timeout).
# `_exceptions` 내부 모듈 import 회피 → public SDK surface만 사용.
# ============================================================================

# 408 Request Timeout, 429 Too Many Requests, 500/502/503/504 server errors,
# 529 Overloaded (anthropic-specific).
_RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504, 529})

_R12_MAX_RETRIES = 3            # 총 4번 시도 (initial + 3 retries)
_R12_BASE_BACKOFF_SECS = 2.0    # 2, 4, 8 secs exponential — 최대 14초 대기


def _is_retryable(exc: BaseException) -> bool:
    """R12: Anthropic 일시 장애 판별.

    True: 일시적 — backoff 후 retry 가치 있음
        - RateLimitError (429)
        - APITimeoutError, APIConnectionError (network)
        - APIStatusError with status ∈ {408, 429, 500, 502, 503, 504, 529}
    False: 영구적 또는 사용자 오류 — 즉시 raise
        - BadRequestError (400), AuthenticationError (401), etc.
        - 일반 Exception (ValueError, bug 등)
    """
    if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        return isinstance(status, int) and status in _RETRYABLE_HTTP_STATUSES
    return False


def _invoke_with_retry(
    chat: ChatAnthropic,
    messages: list[Any],
    *,
    max_retries: int = _R12_MAX_RETRIES,
    base_backoff: float = _R12_BASE_BACKOFF_SECS,
    sleep: Callable[[float], None] = time.sleep,
) -> BaseMessage:
    """R12: ``chat.invoke``에 exponential backoff retry — Anthropic 일시 장애 자동 복구.

    backoff: ``base_backoff * 2^attempt`` (default 2, 4, 8 secs).
    ``_is_retryable``이 False인 예외는 즉시 raise (retry 0).
    모든 retry 소진 시 마지막 예외 raise (호출자에게 전파).
    """
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = chat.invoke(messages)
            if not isinstance(resp, BaseMessage):
                raise TypeError(
                    f"unexpected response type from chat.invoke: {type(resp).__name__}"
                )
            return resp
        except Exception as e:  # noqa: BLE001 — 분류 helper로 위임
            if not _is_retryable(e):
                raise
            last_exc = e
            if attempt == max_retries:
                break
            sleep(base_backoff * (2 ** attempt))
    assert last_exc is not None
    raise last_exc


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
        """``chat.invoke``를 wrap — 응답 반환 + 토큰/비용 계산 + trace 저장.

        P11.2: ``ipe.node.latency_ms / tokens_in / tokens_out / cost_usd`` 4 메트릭을
        ``ipe.observability`` logger로 emit (JsonFormatter가 stdout 라인으로 직렬화).
        """
        self.seq += 1
        seq = self.seq
        ts = datetime.now(UTC).isoformat()

        start = time.perf_counter()
        # R12 (Round 14): Anthropic 일시 장애 (529/429/timeout 등) 자동 retry.
        # _invoke_with_retry는 BaseMessage 반환 보장 + 비-retryable 예외 즉시 raise.
        resp = _invoke_with_retry(chat, messages)
        latency_ms = int((time.perf_counter() - start) * 1000)

        usage = getattr(resp, "usage_metadata", None) or {}
        in_tok = int(usage.get("input_tokens", 0))
        out_tok = int(usage.get("output_tokens", 0))
        model = str(getattr(chat, "model", "unknown"))
        cost = _cost_usd(model, in_tok, out_tok)

        # P11.2 메트릭 emit
        labels = {"node": node, "model": model, "seq": seq}
        emit_metric("ipe.node.latency_ms", latency_ms, **labels)
        emit_metric("ipe.node.tokens_in", in_tok, **labels)
        emit_metric("ipe.node.tokens_out", out_tok, **labels)
        emit_metric("ipe.node.cost_usd", cost, **labels)

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
