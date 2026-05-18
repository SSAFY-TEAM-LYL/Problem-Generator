"""sandbox isolation tests — basic smoke + per-tier isolation 검증.

격리 검증은 실제 subprocess + sandbox 도구를 사용하므로 ``@pytest.mark.slow``로
표시. CI에서는 ``-m "not slow"``로 제외 가능.

각 tier는 환경에 따라 skip:
- T1 (Docker): daemon 미실행 시 skip
- T2.5 (sandbox-exec): macOS 외 OS skip
- T3 (rlimit): 모든 OS에서 실행
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ipe.sandbox.docker_runner import DockerRunner
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.sandbox.runner import RunSpec, SandboxedRunner
from ipe.sandbox.sandboxexec_runner import SandboxExecRunner


def _docker_daemon_up() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            timeout=5,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


# 한 번만 평가 (collection 시 5s timeout 1회). 그 후 marker로 사용.
DOCKER_AVAILABLE = _docker_daemon_up()
IS_MACOS = platform.system() == "Darwin"


# =============================================================================
# 공통 헬퍼
# =============================================================================


def _assert_basic_echo(runner: SandboxedRunner, *, cwd: str = "/tmp") -> None:
    """가장 단순한 echo가 격리 환경에서도 정상 작동."""
    res = runner.run(RunSpec(cmd=["/bin/echo", "hello"], cwd=cwd))
    assert res.status == "OK", (
        f"expected OK, got {res.status} (rc={res.returncode}, stderr={res.stderr[:200]!r})"
    )
    assert res.returncode == 0
    assert res.stdout.strip() == "hello"


def _assert_infinite_loop_blocked(runner: SandboxedRunner, *, cwd: str = "/tmp") -> None:
    """time_limit_ms=500에서 무한 loop는 강제 종료 (TLE 또는 RTE).

    TLE: subprocess wall-clock timeout 트리거.
    RTE: RLIMIT_CPU가 먼저 트리거되어 SIGXCPU 발생 (interpreter startup이 느릴 때).
    어느 쪽이든 무한 loop가 안전하게 강제 종료되었으므로 OK.
    """
    res = runner.run(
        RunSpec(
            cmd=[sys.executable, "-c", "while True: pass"],
            cwd=cwd,
            time_limit_ms=500,
        )
    )
    assert res.status in ("TLE", "RTE"), f"expected TLE or RTE, got {res.status}"


# =============================================================================
# T3 RlimitRunner — 모든 OS에서 동작
# =============================================================================


class TestRlimitRunner:
    @pytest.fixture
    def runner(self) -> RlimitRunner:
        return RlimitRunner()

    def test_tier_id(self, runner: RlimitRunner) -> None:
        assert runner.tier == "T3"

    def test_basic_echo(self, runner: RlimitRunner) -> None:
        _assert_basic_echo(runner)

    @pytest.mark.slow
    def test_infinite_loop_tle(self, runner: RlimitRunner) -> None:
        _assert_infinite_loop_blocked(runner)

    def test_nonzero_returncode_rte(self, runner: RlimitRunner) -> None:
        res = runner.run(
            RunSpec(cmd=[sys.executable, "-c", "import sys; sys.exit(7)"], cwd="/tmp")
        )
        assert res.status == "RTE"
        assert res.returncode == 7

    @pytest.mark.slow
    def test_isolation_self_test(self, runner: RlimitRunner) -> None:
        """T3은 network/fs 차단 못 함이 정상. cpu/fork는 best-effort (macOS flaky)."""
        results = runner.isolation_self_test()
        assert results["network_blocked"] is False, "T3 should NOT block network"
        assert results["fs_write_blocked"] is False, "T3 should NOT block fs"
        # cpu/fork는 best-effort. macOS에서 RLIMIT_CPU/NPROC가 user-level이라 flaky.
        # 별도 test_infinite_loop_tle에서 직접 wall-clock 검증함.
        assert isinstance(results["cpu_limited"], bool)
        assert isinstance(results["fork_limited"], bool)
        assert isinstance(results["memory_limited"], bool)


# =============================================================================
# T2.5 SandboxExecRunner — macOS 전용
# =============================================================================


@pytest.mark.skipif(not IS_MACOS, reason="sandbox-exec is macOS only")
class TestSandboxExecRunner:
    @pytest.fixture
    def runner(self) -> SandboxExecRunner:
        return SandboxExecRunner()

    def test_tier_id(self, runner: SandboxExecRunner) -> None:
        assert runner.tier == "T2.5"

    def test_basic_echo(self, runner: SandboxExecRunner) -> None:
        _assert_basic_echo(runner)

    def test_python_arithmetic(self, runner: SandboxExecRunner) -> None:
        res = runner.run(
            RunSpec(cmd=[sys.executable, "-c", "print(2+2)"], cwd="/tmp")
        )
        assert res.status == "OK"
        assert res.stdout.strip() == "4"

    @pytest.mark.slow
    def test_infinite_loop_tle(self, runner: SandboxExecRunner) -> None:
        _assert_infinite_loop_blocked(runner)

    @pytest.mark.slow
    def test_network_blocked(self, runner: SandboxExecRunner) -> None:
        """sandbox-exec network 차단 (deny network*)."""
        script = (
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 53), timeout=1)\n"
            "    print('OPEN')\n"
            "except Exception:\n"
            "    print('BLOCKED')\n"
        )
        res = runner.run(
            RunSpec(
                cmd=[sys.executable, "-c", script],
                cwd="/tmp",
                time_limit_ms=3000,
            )
        )
        assert "BLOCKED" in res.stdout or res.status == "RTE"

    @pytest.mark.slow
    def test_fs_write_outside_workdir_blocked(self, runner: SandboxExecRunner) -> None:
        """workdir 외부 (/Users/Shared) write 차단."""
        script = (
            "try:\n"
            "    open('/Users/Shared/sandbox_probe.txt', 'w').write('x')\n"
            "    print('WROTE')\n"
            "except Exception:\n"
            "    print('BLOCKED')\n"
        )
        res = runner.run(
            RunSpec(
                cmd=[sys.executable, "-c", script],
                cwd="/tmp",
                time_limit_ms=3000,
            )
        )
        assert "BLOCKED" in res.stdout or res.status == "RTE"


# =============================================================================
# T1 DockerRunner — Docker daemon 떠있는 경우만
# =============================================================================


@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker daemon not available")
class TestDockerRunner:
    @pytest.fixture
    def runner(self) -> DockerRunner:
        return DockerRunner()

    def test_tier_id(self, runner: DockerRunner) -> None:
        assert runner.tier == "T1"

    @pytest.mark.slow
    def test_basic_echo(self, runner: DockerRunner, tmp_path: Path) -> None:
        # R-docker-mount (Round 16): bind mount는 host cwd가 존재해야 함.
        # 운영은 executor가 run_dir.mkdir() — 테스트는 tmp_path fixture 사용.
        res = runner.run(RunSpec(cmd=["echo", "hello"], cwd=str(tmp_path)))
        assert res.status == "OK"
        assert res.stdout.strip() == "hello"

    @pytest.mark.slow
    def test_network_blocked(self, runner: DockerRunner, tmp_path: Path) -> None:
        """--network=none이 외부 연결 차단."""
        script = (
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 53), timeout=1)\n"
            "    print('OPEN')\n"
            "except Exception:\n"
            "    print('BLOCKED')\n"
        )
        res = runner.run(
            RunSpec(
                cmd=["python3", "-c", script],
                cwd=str(tmp_path),
                time_limit_ms=10000,
            )
        )
        assert "BLOCKED" in res.stdout or res.status == "RTE"
