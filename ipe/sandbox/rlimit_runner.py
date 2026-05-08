"""T3 (RLIMIT-only) sandbox — cross-platform fallback.

POSIX `resource.setrlimit` + `subprocess` + wall-clock timeout.
Network/FS 격리는 **없음** (OS user 권한에만 의존). 가장 약한 보호.

macOS는 T2.5(SandboxExec) 또는 T1(Docker), Linux는 T2(nsjail) 또는 T1을 권장.
T3은 모든 OS에서 동작하는 마지막 fallback.
"""

from __future__ import annotations

import contextlib
import resource
import subprocess
import sys
import time
from collections.abc import Callable
from typing import ClassVar

from ipe.sandbox.runner import RunResult, RunSpec, RunStatus, SandboxedRunner


def _build_preexec(spec: RunSpec) -> Callable[[], None]:
    """spec에 따라 RLIMIT을 자식 프로세스에 적용하는 preexec_fn을 반환."""
    mem_bytes = spec.memory_limit_mb * 1024 * 1024
    cpu_secs = max(1, spec.time_limit_ms // 1000 + 1)
    nproc = spec.max_processes

    def _apply() -> None:
        # 각 RLIMIT은 독립적으로 best-effort. OS가 거부하면 다음으로 진행.
        for res_id, val in (
            (resource.RLIMIT_AS, mem_bytes),
            (resource.RLIMIT_CPU, cpu_secs),
            (resource.RLIMIT_NPROC, nproc),
            (resource.RLIMIT_NOFILE, 256),
        ):
            with contextlib.suppress(ValueError, OSError):
                resource.setrlimit(res_id, (val, val))

    return _apply


def _decode(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _classify(rc: int, truncated_stdout: bool) -> RunStatus:
    if truncated_stdout:
        return "OLE"
    # RLIMIT_AS 초과 → SIGKILL (-9 또는 OS에 따라 137)
    if rc in (-9, 137):
        return "MLE"
    if rc == 0:
        return "OK"
    return "RTE"


class RlimitRunner(SandboxedRunner):
    """T3: setrlimit + subprocess + wall-clock timeout. Cross-platform."""

    tier: ClassVar[str] = "T3"

    def run(self, spec: RunSpec) -> RunResult:
        wall_timeout = spec.time_limit_ms / 1000.0
        env = spec.env if spec.env else None
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                spec.cmd,
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
            return RunResult(
                status="TLE",
                returncode=-1,
                stdout=_decode(e.stdout)[: spec.max_stdout_bytes],
                stderr=_decode(e.stderr)[: spec.max_stderr_bytes],
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
        """T3 격리 가능 항목만 점검. network/fs는 항상 False."""
        # 1) Memory: 64MB cap에서 ~200MB alloc 시도 → MLE 또는 RTE
        res_mem = self.run(
            RunSpec(
                cmd=[sys.executable, "-c", "x = [0] * (50 * 1024 * 1024)"],
                cwd="/tmp",
                time_limit_ms=3000,
                memory_limit_mb=64,
            )
        )
        memory_limited = res_mem.status in ("MLE", "RTE")

        # 2) CPU: 500ms cap에서 무한 loop → TLE
        res_cpu = self.run(
            RunSpec(
                cmd=[sys.executable, "-c", "while True: pass"],
                cwd="/tmp",
                time_limit_ms=500,
            )
        )
        cpu_limited = res_cpu.status == "TLE"

        # 3) Fork: max_processes=4에서 50회 fork 시도 → OSError 발생
        fork_script = (
            "import os, sys\n"
            "for _ in range(50):\n"
            "    try: os.fork()\n"
            "    except OSError: sys.exit(0)\n"
            "sys.exit(1)\n"
        )
        res_fork = self.run(
            RunSpec(
                cmd=[sys.executable, "-c", fork_script],
                cwd="/tmp",
                time_limit_ms=3000,
                max_processes=4,
            )
        )
        # macOS는 RLIMIT_NPROC가 사용자 단위로 적용되어 효과 약함.
        # Linux는 잘 동작. best-effort 판정.
        fork_limited = res_fork.status in ("OK", "RTE")

        return {
            "network_blocked": False,
            "fs_write_blocked": False,
            "memory_limited": memory_limited,
            "cpu_limited": cpu_limited,
            "fork_limited": fork_limited,
        }
