"""Sandbox 실행기 추상 인터페이스.

스펙: PROJECT_SPEC.md §4.5.1 (Sandboxing & Resource Limits)
       ARCHITECTURE.md §3.9.0 (SandboxedRunner abstraction)

모든 concrete runner (DockerRunner / SandboxExecRunner / NsjailRunner /
RlimitRunner)는 SandboxedRunner를 상속하여 `run(spec) -> RunResult`와
`isolation_self_test() -> dict` 두 메서드를 구현한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Literal

RunStatus = Literal[
    "OK",             # 정상 종료 (returncode == 0)
    "RTE",            # Runtime Error (returncode != 0, but not other status)
    "TLE",            # Time Limit Exceeded (wall clock 또는 CPU)
    "MLE",            # Memory Limit Exceeded
    "OLE",            # Output Limit Exceeded (stdout > max_stdout_bytes)
    "SANDBOX_ERROR",  # sandbox 자체 실패 (이미지 missing 등)
]


@dataclass(frozen=True)
class RunSpec:
    """실행 사양. concrete runner가 이걸 받아 격리 환경에서 실행."""

    cmd: list[str]                              # 실행할 인자 리스트 (셸 미경유)
    cwd: str                                     # 작업 디렉토리 (절대경로 권장)
    stdin: str = ""
    time_limit_ms: int = 5000                   # CPU + wall, 둘 다 enforce
    memory_limit_mb: int = 512
    max_stdout_bytes: int = 5 * 1024 * 1024     # 5 MB
    max_stderr_bytes: int = 1 * 1024 * 1024     # 1 MB
    max_processes: int = 16                      # RLIMIT_NPROC / --pids-limit
    network: bool = False                        # 항상 False 권장 (T1/T2/T2.5 강제 차단)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    """실행 결과."""

    status: RunStatus
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: int
    peak_memory_mb: int | None = None
    truncated_stdout: bool = False
    truncated_stderr: bool = False


class SandboxedRunner(ABC):
    """모든 격리 실행기의 추상 베이스.

    Concrete subclass에서 `tier` 클래스 변수와 `run`/`isolation_self_test`를 구현.
    """

    #: tier 식별자. concrete subclass에서 override ("T1" | "T2" | "T2.5" | "T3").
    tier: ClassVar[str]

    @abstractmethod
    def run(self, spec: RunSpec) -> RunResult:
        """spec에 따라 격리된 환경에서 실행하고 결과를 반환한다."""

    @abstractmethod
    def isolation_self_test(self) -> dict[str, bool]:
        """의도된 위반 시도가 차단되는지 자체 점검.

        반환 dict의 key는 검사 항목 (예: ``network_blocked``,
        ``fs_write_blocked``, ``fork_limited``, ``memory_limited``,
        ``cpu_limited``), value는 해당 항목이 정책대로 작동하는지 여부.
        """
