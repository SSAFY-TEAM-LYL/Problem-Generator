"""구조적 로깅 (P11.1) — JSON formatter + setup_logging.

스펙: ARCHITECTURE.md §3.12, IMPLEMENTATION_ROADMAP §1 P11.1

한 줄 = 한 JSON record (stdout). LLMCallTracker는 ``ipe.observability`` 로거를
통해 ``extra={"metric": ..., "value": ..., **labels}`` 형태로 메트릭도 emit.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# logging.LogRecord 표준 attribute set — extra={...} 키들과 분리
_LOGRECORD_STD_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
})


class JsonFormatter(logging.Formatter):
    """LogRecord → 한 줄 JSON {ts, level, logger, message, [exc], **extra}.

    ``ts`` 는 ISO8601 UTC ms-precision (예: ``"2026-05-09T16:30:00.000Z"``).
    멀티라인 message는 JSON string escape, exc_info는 ``exc`` 필드.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"
        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _LOGRECORD_STD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", *, stream: Any = None) -> None:
    """Root logger를 JsonFormatter + StreamHandler(stdout)로 (재)설정.

    ``stream`` 으로 ``StringIO`` 등 주입 가능 (테스트). 기존 root handler는
    모두 제거 후 1개로 교체.
    """
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
