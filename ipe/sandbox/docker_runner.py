"""T1 (Docker) — production-grade sandbox.

``docker run --rm --network=none --read-only --tmpfs --memory --cpus --pids-limit``
로 컨테이너 격리. 모든 OS에서 가장 강력한 보호.

Docker daemon이 안 떠 있거나 Docker가 미설치면 인스턴스화 시 RuntimeError.
P1.5에서 ``Dockerfile``을 추가하면 ``ipe-sandbox:latest`` 이미지로 교체.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import ClassVar

from ipe.sandbox.runner import RunResult, RunSpec, RunStatus, SandboxedRunner

DEFAULT_IMAGE = "python:3.11-slim"  # P1.5에서 ipe-sandbox:latest로 교체
DOCKER_OVERHEAD_SECS = 10.0          # 컨테이너 startup overhead 보강


def _classify(rc: int, truncated_stdout: bool) -> RunStatus:
    if truncated_stdout:
        return "OLE"
    if rc == 137:
        # 137 = 128 + SIGKILL(9). Docker memory limit 초과 시 OOM-killer 발동.
        return "MLE"
    if rc == 0:
        return "OK"
    return "RTE"


class DockerRunner(SandboxedRunner):
    """T1: Docker 컨테이너. cross-platform, production-grade."""

    tier: ClassVar[str] = "T1"

    def __init__(self, image: str = DEFAULT_IMAGE) -> None:
        self.image = image
        # Docker daemon 가용성 확인 (init 시점)
        try:
            subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"Docker daemon not available: {e}") from e

    def run(self, spec: RunSpec) -> RunResult:
        # R-docker-workdir (Round 15): Docker는 --workdir와 -v에 절대경로 필수.
        # 자체 방어로 절대화.
        cwd_abs = str(Path(spec.cwd).resolve())
        cmd = [
            "docker", "run", "--rm",
            "--network=none",
            "--read-only",
            # R-docker-mount (Round 16): 기존 --tmpfs={cwd}는 그 경로 위에 빈 tmpfs를
            # 오버레이 마운트 → 호스트의 solution.py가 mask되어 컨테이너에서
            # "python3: can't open file ..." RTE (Round 15 e2e 측정에서 발견).
            # bind mount(-v)로 변경: 호스트 cwd를 컨테이너의 같은 경로에 r/w로 마운트.
            # --read-only rootfs는 유지 → 다른 곳 못 쓰지만 cwd는 writable.
            "-v", f"{cwd_abs}:{cwd_abs}:rw",
            f"--memory={spec.memory_limit_mb}m",
            f"--memory-swap={spec.memory_limit_mb}m",
            "--cpus=1",
            f"--pids-limit={spec.max_processes}",
            f"--workdir={cwd_abs}",
            "-i",
            self.image,
            *spec.cmd,
        ]

        wall_timeout = spec.time_limit_ms / 1000.0 + DOCKER_OVERHEAD_SECS
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                input=spec.stdin,
                capture_output=True,
                text=True,
                timeout=wall_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            stdout = e.stdout if isinstance(e.stdout, str) else ""
            stderr = e.stderr if isinstance(e.stderr, str) else ""
            return RunResult(
                status="TLE",
                returncode=-1,
                stdout=stdout[: spec.max_stdout_bytes],
                stderr=stderr[: spec.max_stderr_bytes],
                elapsed_ms=elapsed_ms,
            )

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        raw_stdout = proc.stdout or ""
        raw_stderr = proc.stderr or ""
        truncated_stdout = len(raw_stdout) > spec.max_stdout_bytes
        truncated_stderr = len(raw_stderr) > spec.max_stderr_bytes

        return RunResult(
            status=_classify(proc.returncode, truncated_stdout),
            returncode=proc.returncode,
            stdout=raw_stdout[: spec.max_stdout_bytes],
            stderr=raw_stderr[: spec.max_stderr_bytes],
            elapsed_ms=elapsed_ms,
            truncated_stdout=truncated_stdout,
            truncated_stderr=truncated_stderr,
        )

    def isolation_self_test(self) -> dict[str, bool]:
        """Docker 격리 검증 — 5 probe (network/fs/memory/cpu/fork)."""
        # cwd는 컨테이너 내부 경로 (/work — Dockerfile WORKDIR 또는 임의)
        cwd = "/work"

        # 1) Network: 외부 host 연결 → 차단 (--network=none)
        network_script = (
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 53), timeout=1)\n"
            "    print('NETWORK_OK')\n"
            "except Exception:\n"
            "    print('NETWORK_BLOCKED')\n"
        )
        res_net = self.run(
            RunSpec(
                cmd=["python3", "-c", network_script],
                cwd=cwd,
                time_limit_ms=10000,
            )
        )
        network_blocked = "NETWORK_BLOCKED" in res_net.stdout

        # 2) FS write: rootfs read-only — workdir 외부 write 차단
        fs_script = (
            "try:\n"
            "    open('/etc/passwd_probe', 'w').write('x')\n"
            "    print('FS_WRITE_OK')\n"
            "except Exception:\n"
            "    print('FS_WRITE_BLOCKED')\n"
        )
        res_fs = self.run(
            RunSpec(
                cmd=["python3", "-c", fs_script],
                cwd=cwd,
                time_limit_ms=10000,
            )
        )
        fs_write_blocked = "FS_WRITE_BLOCKED" in res_fs.stdout

        # 3) Memory: 64MB cap에서 ~200MB alloc → MLE (rc=137)
        res_mem = self.run(
            RunSpec(
                cmd=["python3", "-c", "x = [0] * (50 * 1024 * 1024)"],
                cwd=cwd,
                time_limit_ms=10000,
                memory_limit_mb=64,
            )
        )
        memory_limited = res_mem.status in ("MLE", "RTE")

        # 4) CPU: 1초 cap에서 무한 loop → TLE
        res_cpu = self.run(
            RunSpec(
                cmd=["python3", "-c", "while True: pass"],
                cwd=cwd,
                time_limit_ms=1000,
            )
        )
        cpu_limited = res_cpu.status == "TLE"

        # 5) Fork: --pids-limit=4에서 50 fork → OSError
        fork_script = (
            "import os, sys\n"
            "for _ in range(50):\n"
            "    try: os.fork()\n"
            "    except OSError: sys.exit(0)\n"
            "sys.exit(1)\n"
        )
        res_fork = self.run(
            RunSpec(
                cmd=["python3", "-c", fork_script],
                cwd=cwd,
                time_limit_ms=10000,
                max_processes=4,
            )
        )
        fork_limited = res_fork.status in ("OK", "RTE")

        return {
            "network_blocked": network_blocked,
            "fs_write_blocked": fs_write_blocked,
            "memory_limited": memory_limited,
            "cpu_limited": cpu_limited,
            "fork_limited": fork_limited,
        }
