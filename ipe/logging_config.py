"""구조적 로깅 설정 (P11.1) — JSON formatter + setup_logging.

스펙: ARCHITECTURE.md §3.12 (observability 확장), IMPLEMENTATION_ROADMAP §1 P11.1

운영 환경에서 로그 수집기(Datadog/CloudWatch/ELK 등)가 파싱할 수 있도록
한 줄에 한 JSON record 형식으로 stdout에 emit.

JSON 라인 예시::

    {"ts": "2026-05-09T16:30:00.000Z", "level": "INFO", "logger": "ipe.node",
     "message": "architect completed", "node": "architect", "iter": 1}

LLMCallTracker가 ``logger.info(..., extra={"metric": "ipe.node.latency_ms",
"value": 123, "node": "architect"})`` 형태로 메트릭도 같은 채널에 emit.

Usage::

    from ipe.logging_config import setup_logging
    setup_logging(level="INFO")
    import logging
    logger = logging.getLogger("ipe.node.architect")
    logger.info("done", extra={"node": "architect", "iter": 1})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# logger record의 표준 attribute — extra와 분리하기 위함
_LOGRECORD_STD_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
})


class JsonFormatter(logging.Formatter):
    """logging.Formatter를 상속해 한 줄에 한 JSON record를 emit.

    출력 schema:
    - ``ts``: ISO8601 UTC timestamp (millisecond precision)
    - ``level``: 로그 레벨 (INFO/WARNING/ERROR/...)
    - ``logger``: logger 이름 (예: ``ipe.node.architect``)
    - ``message``: 사람이 읽을 메시지
    - 그 외: ``logger.info(..., extra={...})`` 의 모든 키 (metric/node/iter 등)

    멀티라인 message는 ``\\n``을 그대로 JSON 문자열로 escape.
    exc_info가 있으면 ``exc`` 필드로 traceback 문자열 추가.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"  # ms precision
        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # extra={} 키들을 합침 (LogRecord 표준 attribute 제외)
        for key, value in record.__dict__.items():
            if key in _LOGRECORD_STD_ATTRS:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", *, stream: Any = None) -> None:
    """Root logger를 ``JsonFormatter`` + StreamHandler(stdout)로 설정.

    Args:
        level: 로그 레벨 ("DEBUG"/"INFO"/"WARNING"/"ERROR")
        stream: 출력 stream — 기본 ``sys.stdout``. 테스트에서 StringIO 주입 가능.

    이미 root에 handler가 붙어 있으면 모두 제거하고 다시 설정한다.
    """
    target = stream if stream is not None else sys.stdout
    handler = logging.StreamHandler(target)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
