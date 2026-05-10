"""``ipe._tracing.setup_tracing`` 단위 테스트 (polish round 3 — F4 해소).

스펙: ARCHITECTURE.md §3.12, IMPLEMENTATION_ROADMAP §1 P11.3 (옵션)
범위: ``IPE_LANGSMITH`` / ``IPE_OTEL_ENDPOINT`` 환경변수 toggle 분기.

opentelemetry SDK 미설치 환경에서는 OTel branch가 warn-only path로만 cover됨.
"""

from __future__ import annotations

import logging
import os

import pytest

from ipe._tracing import _setup_otel, setup_tracing


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """모든 IPE_*/LANGCHAIN_*/LANGSMITH_* 환경변수를 테스트마다 초기화."""
    for key in (
        "IPE_LANGSMITH", "IPE_OTEL_ENDPOINT",
        "LANGCHAIN_API_KEY", "LANGSMITH_API_KEY",
        "LANGSMITH_TRACING", "LANGSMITH_PROJECT",
    ):
        monkeypatch.delenv(key, raising=False)


class TestSetupTracingNoOp:
    def test_unset_env_returns_disabled(self) -> None:
        """모든 env unset → 둘 다 disabled."""
        result = setup_tracing()
        assert result == {"langsmith": False, "otel": False}


class TestLangsmith:
    def test_enabled_with_langchain_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IPE_LANGSMITH=1 + LANGCHAIN_API_KEY → activated."""
        monkeypatch.setenv("IPE_LANGSMITH", "1")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "test-key")

        result = setup_tracing()

        assert result["langsmith"] is True
        # side effect: LANGSMITH_TRACING + LANGSMITH_PROJECT set
        assert os.environ["LANGSMITH_TRACING"] == "true"
        assert os.environ["LANGSMITH_PROJECT"] == "ipe"

    def test_enabled_with_langsmith_api_key_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LANGSMITH_API_KEY (alias)도 인정."""
        monkeypatch.setenv("IPE_LANGSMITH", "1")
        monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

        result = setup_tracing()
        assert result["langsmith"] is True

    def test_disabled_without_api_key_warns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """IPE_LANGSMITH=1 + API key 부재 → disabled + warn."""
        monkeypatch.setenv("IPE_LANGSMITH", "1")
        caplog.set_level(logging.WARNING, logger="ipe.tracing")

        result = setup_tracing()

        assert result["langsmith"] is False
        assert any(
            "LANGCHAIN_API_KEY/LANGSMITH_API_KEY missing" in rec.message
            for rec in caplog.records
        )

    def test_disabled_when_ipe_langsmith_not_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IPE_LANGSMITH != "1" → 무시."""
        monkeypatch.setenv("IPE_LANGSMITH", "true")  # "1" 아님
        monkeypatch.setenv("LANGCHAIN_API_KEY", "test-key")

        result = setup_tracing()
        assert result["langsmith"] is False

    def test_existing_project_env_preserved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LANGSMITH_PROJECT가 이미 set이면 setdefault로 보존."""
        monkeypatch.setenv("IPE_LANGSMITH", "1")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")
        monkeypatch.setenv("LANGSMITH_PROJECT", "custom-project")

        setup_tracing()
        assert os.environ["LANGSMITH_PROJECT"] == "custom-project"


class TestOtel:
    def test_disabled_when_endpoint_unset(self) -> None:
        result = setup_tracing()
        assert result["otel"] is False

    def test_warns_when_sdk_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """IPE_OTEL_ENDPOINT 설정됐으나 opentelemetry SDK 미설치 → warn-only.

        SDK 설치 환경에서는 enabled — 둘 다 valid (본 환경 의존).
        """
        monkeypatch.setenv("IPE_OTEL_ENDPOINT", "http://localhost:4318")
        caplog.set_level(logging.WARNING, logger="ipe.tracing")

        result = setup_tracing()

        if not result["otel"]:
            assert any(
                "opentelemetry SDK" in rec.message for rec in caplog.records
            )

    def test_setup_otel_returns_false_on_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_setup_otel`` 직접 호출 — SDK 미설치 시 False (sys.modules에 None inject)."""
        import sys

        # opentelemetry가 설치되었더라도 mock으로 ImportError 강제
        for mod in list(sys.modules.keys()):
            if mod.startswith("opentelemetry"):
                monkeypatch.setitem(sys.modules, mod, None)

        result = _setup_otel("http://x:4318")
        assert result is False


class TestBothEnabled:
    def test_independent_toggles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LangSmith + OTel은 독립적 — 한 쪽만 활성화 가능."""
        monkeypatch.setenv("IPE_LANGSMITH", "1")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")
        # OTEL_ENDPOINT는 unset

        result = setup_tracing()
        assert result["langsmith"] is True
        assert result["otel"] is False
