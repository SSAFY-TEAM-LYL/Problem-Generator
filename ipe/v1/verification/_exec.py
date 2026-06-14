"""Tier B 검증 공용 실행 헬퍼 — code 를 stdin 에 sandbox 실행 (Phase 3 M1).

differential / metamorphic 이 공유. ``runner`` 는 ``ExecutorRunner`` sub-set
(``run(RunSpec) -> RunResult``) — 단위 테스트는 mock 주입.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Protocol

from ipe.sandbox.runner import RunResult, RunSpec

DEFAULT_TIME_LIMIT_MS = 2000
DEFAULT_MEMORY_LIMIT_MB = 256


def exception_signal(stderr: str, limit: int) -> str:
    """stderr 에서 진단 신호 추출 — 트레이스백은 **마지막 줄**(예외 타입)이 핵심.

    Python 트레이스백은 'Traceback ...' + File 프레임들 + 마지막 줄에 예외
    (``IndexError: ...`` 등)가 온다. head truncate 는 프레임 경로만 남기고 정작
    예외 타입을 버린다 → 마지막 비어있지 않은 줄 우선 (없으면 빈 문자열).
    공용 위치(reconcile diagnostics + verification sample 진단 공유)."""
    lines = [ln.strip() for ln in stderr.strip().splitlines() if ln.strip()]
    if not lines:
        return ""
    last = lines[-1]
    return last if len(last) <= limit else last[:limit] + "…"


class CodeRunner(Protocol):
    """``ExecutorRunner`` 와 동일 sub-set — 의존 분리 위해 로컬 재정의."""

    def run(self, spec: RunSpec) -> RunResult: ...


def run_code(
    runner: CodeRunner,
    code: str,
    stdin: str,
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> RunResult:
    """workdir 에 sol.py write 후 sandbox 실행 (executor 패턴과 동일)."""
    with tempfile.TemporaryDirectory() as wd:
        (Path(wd) / "sol.py").write_text(code, encoding="utf-8")
        spec = RunSpec(
            cmd=["python3", "sol.py"],
            cwd=wd,
            stdin=stdin,
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )
        return runner.run(spec)
