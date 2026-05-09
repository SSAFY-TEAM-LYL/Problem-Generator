"""구조적 로깅 단위 테스트 (P11.4).

스펙: ARCHITECTURE.md §3.12, IMPLEMENTATION_ROADMAP §1 P11.4
범위:
- ``JsonFormatter`` 일반 record / extra / 멀티라인 / exc_info / non-JSON 값
- ``setup_logging`` handler 교체 + level 설정
- ``emit_metric`` JSON line 형식 검증
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pytest

from ipe.logging_config import JsonFormatter, setup_logging
from ipe.observability import emit_metric

# =============================================================================
# JsonFormatter 단위
# =============================================================================


class TestJsonFormatter:
    def _make_record(
        self,
        msg: str = "hello",
        *,
        level: int = logging.INFO,
        name: str = "ipe.test",
        extra: dict[str, object] | None = None,
    ) -> logging.LogRecord:
        record = logging.LogRecord(
            name=name, level=level, pathname="x.py", lineno=1,
            msg=msg, args=None, exc_info=None,
        )
        if extra:
            for k, v in extra.items():
                setattr(record, k, v)
        return record

    def test_basic_record(self) -> None:
        formatter = JsonFormatter()
        record = self._make_record()
        out = json.loads(formatter.format(record))

        assert out["level"] == "INFO"
        assert out["logger"] == "ipe.test"
        assert out["message"] == "hello"
        assert "ts" in out
        # ISO8601 UTC ms precision: "YYYY-MM-DDTHH:MM:SS.sssZ"
        assert out["ts"].endswith("Z")
        assert "T" in out["ts"]

    def test_extra_fields_included(self) -> None:
        """logger.info(..., extra={...}) 의 키들이 JSON에 그대로 합쳐짐."""
        formatter = JsonFormatter()
        record = self._make_record(
            extra={"node": "architect", "iter": 3, "metric": "ipe.node.latency_ms"}
        )
        out = json.loads(formatter.format(record))
        assert out["node"] == "architect"
        assert out["iter"] == 3
        assert out["metric"] == "ipe.node.latency_ms"

    def test_multiline_message_escaped(self) -> None:
        formatter = JsonFormatter()
        record = self._make_record(msg="line1\nline2\nline3")
        line = formatter.format(record)
        # 출력은 한 줄이어야 함 (멀티라인 message는 JSON string escape)
        assert "\n" not in line
        out = json.loads(line)
        assert out["message"] == "line1\nline2\nline3"

    def test_exc_info_serialized(self) -> None:
        import sys

        formatter = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="ipe.x", level=logging.ERROR, pathname="x.py", lineno=1,
            msg="failure", args=None, exc_info=exc_info,
        )
        out = json.loads(formatter.format(record))
        assert "exc" in out
        assert "ValueError" in out["exc"]
        assert "boom" in out["exc"]

    def test_non_json_serializable_value_falls_back_to_str(self) -> None:
        """default=str로 Path 등도 안전하게 직렬화."""
        formatter = JsonFormatter()
        record = self._make_record(extra={"path": Path("/tmp/x.json")})
        out = json.loads(formatter.format(record))
        assert "path" in out
        assert isinstance(out["path"], str)


# =============================================================================
# setup_logging
# =============================================================================


class TestSetupLogging:
    def test_replaces_root_handlers(self) -> None:
        root = logging.getLogger()
        # 더미 handler 추가
        dummy = logging.StreamHandler()
        root.addHandler(dummy)

        setup_logging(level="INFO")
        # setup_logging이 모든 기존 handler를 제거하고 1개만 남김
        assert len(root.handlers) == 1
        assert dummy not in root.handlers
        # JsonFormatter가 부착됨
        assert isinstance(root.handlers[0].formatter, JsonFormatter)

    def test_level_is_applied(self) -> None:
        setup_logging(level="DEBUG")
        assert logging.getLogger().level == logging.DEBUG
        setup_logging(level="WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_stream_injection_captures_output(self) -> None:
        """stream 인자로 StringIO 주입 → JSON 라인 캡처 + 파싱 가능."""
        buf = io.StringIO()
        setup_logging(level="INFO", stream=buf)

        logger = logging.getLogger("ipe.test_capture")
        logger.info("hello", extra={"node": "architect"})

        text = buf.getvalue().strip()
        # 한 줄에 한 JSON record
        assert "\n" not in text or text.count("\n") == 0
        out = json.loads(text)
        assert out["message"] == "hello"
        assert out["node"] == "architect"


# =============================================================================
# emit_metric
# =============================================================================


def test_emit_metric_writes_record(caplog: pytest.LogCaptureFixture) -> None:
    """emit_metric → ipe.observability logger record + extra={metric, value, **labels}."""
    caplog.set_level(logging.INFO, logger="ipe.observability")
    emit_metric(
        "ipe.node.latency_ms", 123,
        node="architect", model="claude-opus-4-7", seq=1,
    )
    assert len(caplog.records) == 1
    rec = caplog.records[0]
    assert rec.name == "ipe.observability"
    assert rec.message == "metric"
    # extra는 LogRecord attribute로 추가됨
    assert rec.metric == "ipe.node.latency_ms"  # type: ignore[attr-defined]
    assert rec.value == 123  # type: ignore[attr-defined]
    assert rec.node == "architect"  # type: ignore[attr-defined]
    assert rec.model == "claude-opus-4-7"  # type: ignore[attr-defined]
    assert rec.seq == 1  # type: ignore[attr-defined]


def test_emit_metric_through_json_formatter() -> None:
    """emit_metric → setup_logging의 JsonFormatter를 통해 JSON 라인으로 직렬화."""
    buf = io.StringIO()
    setup_logging(level="INFO", stream=buf)

    emit_metric("ipe.node.cost_usd", 0.0123, node="coder", seq=2)

    text = buf.getvalue().strip()
    out = json.loads(text)
    assert out["metric"] == "ipe.node.cost_usd"
    assert out["value"] == 0.0123
    assert out["node"] == "coder"
    assert out["seq"] == 2
