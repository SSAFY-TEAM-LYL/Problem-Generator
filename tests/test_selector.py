"""Unit tests for ipe.sandbox.selector — pick_runner() 분기 검증."""

from __future__ import annotations

import platform
from unittest.mock import patch

import pytest

from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.sandbox.sandboxexec_runner import SandboxExecRunner
from ipe.sandbox.selector import pick_runner

IS_MACOS = platform.system() == "Darwin"


class TestExplicitTiers:
    """tier 명시 — 해당 runner 직접 인스턴스화."""

    def test_rlimit_returns_t3(self) -> None:
        runner = pick_runner("rlimit")
        assert isinstance(runner, RlimitRunner)
        assert runner.tier == "T3"

    @pytest.mark.skipif(not IS_MACOS, reason="sandbox-exec is macOS only")
    def test_sandboxexec_returns_t2_5(self) -> None:
        runner = pick_runner("sandboxexec")
        assert isinstance(runner, SandboxExecRunner)
        assert runner.tier == "T2.5"


class TestAutoSelection:
    """tier='auto' — OS-aware fallback."""

    def test_auto_falls_back_to_rlimit_when_no_alternatives(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Linux + docker/nsjail 모두 없음 → T3 fallback."""
        monkeypatch.setattr("shutil.which", lambda x: None)
        monkeypatch.setattr("platform.system", lambda: "Linux")
        runner = pick_runner("auto")
        assert isinstance(runner, RlimitRunner)

    def test_auto_picks_sandboxexec_on_macos_no_docker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """macOS + docker 미설치 + sandbox-exec 있음 → T2.5."""
        monkeypatch.setattr(
            "shutil.which",
            lambda x: "/usr/bin/sandbox-exec" if x == "sandbox-exec" else None,
        )
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        runner = pick_runner("auto")
        assert isinstance(runner, SandboxExecRunner)

    def test_auto_skips_docker_if_daemon_down_macos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """macOS + docker 바이너리 있지만 daemon down + sandbox-exec 있음 → T2.5."""
        monkeypatch.setattr(
            "shutil.which",
            lambda x: f"/usr/bin/{x}" if x in ("docker", "sandbox-exec") else None,
        )
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        with patch(
            "ipe.sandbox.docker_runner.subprocess.run",
            side_effect=FileNotFoundError("daemon down"),
        ):
            runner = pick_runner("auto")
        assert isinstance(runner, SandboxExecRunner)

    def test_auto_skips_docker_then_falls_to_rlimit_linux(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Linux + docker daemon down + nsjail 미구현 → T3 fallback."""
        monkeypatch.setattr(
            "shutil.which",
            lambda x: "/usr/bin/docker" if x == "docker" else None,
        )
        monkeypatch.setattr("platform.system", lambda: "Linux")
        with patch(
            "ipe.sandbox.docker_runner.subprocess.run",
            side_effect=FileNotFoundError("daemon down"),
        ):
            runner = pick_runner("auto")
        assert isinstance(runner, RlimitRunner)
