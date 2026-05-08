"""T2.5 (macOS sandbox-exec) — Apple Sandbox profile + RLIMIT.

``sandbox-exec``는 Apple이 deprecated로 표시했으나 macOS 26 (2026)에서도 동작.
- network 차단 (deny default)
- workdir 외부 write 차단
- RLIMIT으로 memory·CPU cap

Linux/Windows에서는 인스턴스화 시 RuntimeError.
"""

from __future__ import annotations

import contextlib
import platform
import resource
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from ipe.sandbox.runner import RunResult, RunSpec, RunStatus, SandboxedRunner


def _build_profile(workdir: str) -> str:
    """sandbox-exec용 profile (S-expression DSL).

    workdir 내부는 read/write, /tmp는 read/write 허용. 그 외 시스템 라이브러리와
    /Users는 read만 (venv binary 등을 호출 가능하게). network는 default deny.
    """
    return f"""(version 1)
(deny default)

;; 프로세스 라이프사이클
(allow process-fork)
(allow process-exec)
(allow signal (target self))

;; sysctl / mach / ioctl
(allow sysctl-read)
(allow mach-lookup)
(allow file-ioctl)

;; 시스템 라이브러리/바이너리 read
(allow file-read* (subpath "/usr"))
(allow file-read* (subpath "/System"))
(allow file-read* (subpath "/Library"))
(allow file-read* (subpath "/opt"))
(allow file-read* (subpath "/private/var"))
(allow file-read* (subpath "/private/etc"))
(allow file-read* (subpath "/Users"))

;; workdir + tmp는 read/write
(allow file-read* (subpath "{workdir}"))
(allow file-write* (subpath "{workdir}"))
(allow file-read* (subpath "/private/tmp"))
(allow file-write* (subpath "/private/tmp"))
(allow file-read* (subpath "/tmp"))
(allow file-write* (subpath "/tmp"))
"""


def _build_preexec(spec: RunSpec) -> Callable[[], None]:
    mem_bytes = spec.memory_limit_mb * 1024 * 1024
    cpu_secs = max(1, spec.time_limit_ms // 1000 + 1)

    def _apply() -> None:
        for res_id, val in (
            (resource.RLIMIT_AS, mem_bytes),
            (resource.RLIMIT_CPU, cpu_secs),
        ):
            with contextlib.suppress(ValueError, OSError):
                resource.setrlimit(res_id, (val, val))

    return _apply


def _classify(rc: int, truncated_stdout: bool) -> RunStatus:
    if truncated_stdout:
        return "OLE"
    if rc in (-9, 137):
        return "MLE"
    if rc == 0:
        return "OK"
    return "RTE"


class SandboxExecRunner(SandboxedRunner):
    """T2.5: sandbox-exec + RLIMIT. macOS 전용."""

    tier: ClassVar[str] = "T2.5"

    def __init__(self) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError("SandboxExecRunner is macOS-only")

    def run(self, spec: RunSpec) -> RunResult:
        profile_text = _build_profile(spec.cwd)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sb", delete=False, encoding="utf-8"
        ) as f:
            f.write(profile_text)
            profile_path = f.name

        try:
            wrapped = ["sandbox-exec", "-f", profile_path, *spec.cmd]
            wall_timeout = spec.time_limit_ms / 1000.0
            env = spec.env if spec.env else None
            start = time.perf_counter()
            try:
                proc = subprocess.run(
                    wrapped,
                    cwd=spec.cwd,
                    input=spec.stdin,
                    capture_output=True,
                    text=True,
                    timeout=wall_timeout,
                    preexec_fn=_build_preexec(spec),
                    env=env,
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
        finally:
            Path(profile_path).unlink(missing_ok=True)

    def isolation_self_test(self) -> dict[str, bool]:
        """sandbox-exec 격리 검증 — network/fs/memory/cpu."""
        # 1) Network: 외부 host 연결 시도 → 차단
        network_script = (
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 53), timeout=1)\n"
            "    print('NETWORK_OK')\n"
            "except Exception as e:\n"
            "    print('NETWORK_BLOCKED:' + type(e).__name__)\n"
        )
        res_net = self.run(
            RunSpec(
                cmd=[sys.executable, "-c", network_script],
                cwd="/tmp",
                time_limit_ms=3000,
            )
        )
        network_blocked = "NETWORK_BLOCKED" in res_net.stdout

        # 2) FS write: workdir 외부에 write 시도 → 차단
        fs_script = (
            "try:\n"
            "    open('/Users/Shared/sandbox_probe.txt', 'w').write('x')\n"
            "    print('FS_WRITE_OK')\n"
            "except Exception as e:\n"
            "    print('FS_WRITE_BLOCKED:' + type(e).__name__)\n"
        )
        res_fs = self.run(
            RunSpec(
                cmd=[sys.executable, "-c", fs_script],
                cwd="/tmp",
                time_limit_ms=3000,
            )
        )
        fs_write_blocked = "FS_WRITE_BLOCKED" in res_fs.stdout

        # 3) Memory: 64MB cap에서 ~200MB alloc → MLE/RTE
        res_mem = self.run(
            RunSpec(
                cmd=[sys.executable, "-c", "x = [0] * (50 * 1024 * 1024)"],
                cwd="/tmp",
                time_limit_ms=3000,
                memory_limit_mb=64,
            )
        )
        memory_limited = res_mem.status in ("MLE", "RTE")

        # 4) CPU: 500ms cap에서 무한 loop → TLE
        res_cpu = self.run(
            RunSpec(
                cmd=[sys.executable, "-c", "while True: pass"],
                cwd="/tmp",
                time_limit_ms=500,
            )
        )
        cpu_limited = res_cpu.status == "TLE"

        return {
            "network_blocked": network_blocked,
            "fs_write_blocked": fs_write_blocked,
            "memory_limited": memory_limited,
            "cpu_limited": cpu_limited,
            "fork_limited": False,  # sandbox-exec 자체는 fork limit 미지원
        }
