"""Trace export toggle (P11.3 / F4) — LangSmith + OpenTelemetry 옵션.

스펙: ARCHITECTURE.md §3.12, IMPLEMENTATION_ROADMAP §1 P11.3 (옵션)

환경변수 기반 toggle:
- ``IPE_LANGSMITH=1`` + ``LANGCHAIN_API_KEY`` 또는 ``LANGSMITH_API_KEY`` 설정 시
  → langchain이 자동으로 LangSmith에 trace 전송 (``LANGSMITH_TRACING=true`` set).
- ``IPE_OTEL_ENDPOINT=<otlp-collector-url>`` 설정 시 → opentelemetry SDK가 있으면
  TracerProvider + OTLPSpanExporter 활성화. SDK 미설치 시 warn.

운영 환경 도입용 — dev에서는 둘 다 unset이면 no-op.

Usage::

    from ipe._tracing import setup_tracing
    setup_tracing()  # main.py에서 setup_logging() 직후 호출
"""

from __future__ import annotations

import logging
import os
from typing import TypedDict

_logger = logging.getLogger("ipe.tracing")


class TracingState(TypedDict):
    langsmith: bool
    otel: bool


def setup_tracing() -> TracingState:
    """환경변수 read → LangSmith / OTel 활성화.

    Returns:
        ``{"langsmith": bool, "otel": bool}`` — 각 export 활성화 여부.

    side effect:
        - LangSmith 활성화 시 ``LANGSMITH_TRACING=true`` 환경변수 set.
        - OTel 활성화 시 ``opentelemetry.trace.set_tracer_provider`` 호출.
    """
    enabled: TracingState = {"langsmith": False, "otel": False}

    if os.environ.get("IPE_LANGSMITH") == "1":
        if os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY"):
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ.setdefault("LANGSMITH_PROJECT", "ipe")
            enabled["langsmith"] = True
            _logger.info(
                "langsmith tracing enabled",
                extra={"project": os.environ["LANGSMITH_PROJECT"]},
            )
        else:
            _logger.warning(
                "IPE_LANGSMITH=1 set but LANGCHAIN_API_KEY/LANGSMITH_API_KEY missing — skip"
            )

    otel_endpoint = os.environ.get("IPE_OTEL_ENDPOINT")
    if otel_endpoint:
        if _setup_otel(otel_endpoint):
            enabled["otel"] = True
            _logger.info(
                "otel tracing enabled", extra={"endpoint": otel_endpoint}
            )
        else:
            _logger.warning(
                f"IPE_OTEL_ENDPOINT={otel_endpoint} set but opentelemetry SDK "
                "not installed — pip install opentelemetry-sdk "
                "opentelemetry-exporter-otlp"
            )

    return enabled


def _setup_otel(endpoint: str) -> bool:
    """OpenTelemetry TracerProvider 설정. SDK 미설치 시 ``False`` 반환.

    opentelemetry는 optional dependency — mypy strict ignore (운영 환경에서만 설치).
    """
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
            BatchSpanProcessor,
        )
    except ImportError:
        return False

    resource = Resource.create({"service.name": "ipe"})
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    return True
