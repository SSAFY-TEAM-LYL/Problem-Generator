"""sandbox tier 자동 선택. OS-aware fallback.

스펙: PROJECT_SPEC.md §4.5.1 (OS별 자동 선택)
- macOS:  T1(docker) → T2.5(sandboxexec) → T3(rlimit)+경고
- Linux:  T1(docker) → T2(nsjail, 미구현) → T3(rlimit)
- Windows: T1(docker) → T3(rlimit)+경고
"""

from __future__ import annotations

import platform
import shutil
import sys
from typing import Literal

from ipe.sandbox.runner import SandboxedRunner

TierArg = Literal["auto", "docker", "sandboxexec", "rlimit"]


def pick_runner(tier_arg: TierArg = "auto", verbose: bool = False) -> SandboxedRunner:
    """tier_arg에 따라 runner 인스턴스를 반환.

    명시 tier (docker/sandboxexec/rlimit)는 해당 runner 직접 인스턴스화.
    'auto'는 OS-aware 우선순위로 시도하고 실패 시 fallback.
    """
    if tier_arg == "docker":
        from ipe.sandbox.docker_runner import DockerRunner
        return DockerRunner()
    if tier_arg == "sandboxexec":
        from ipe.sandbox.sandboxexec_runner import SandboxExecRunner
        return SandboxExecRunner()
    if tier_arg == "rlimit":
        from ipe.sandbox.rlimit_runner import RlimitRunner
        return RlimitRunner()

    # auto: OS-aware 우선순위 시도
    system = platform.system()

    # 1) T1 Docker — 모든 OS에서 가장 강력
    if shutil.which("docker"):
        try:
            from ipe.sandbox.docker_runner import DockerRunner
            return DockerRunner()
        except RuntimeError as e:
            if verbose:
                print(f"docker tier skipped: {e}", file=sys.stderr)

    # 2) T2.5 macOS sandbox-exec
    if system == "Darwin" and shutil.which("sandbox-exec"):
        from ipe.sandbox.sandboxexec_runner import SandboxExecRunner
        return SandboxExecRunner()

    # 3) (Future) T2 Linux nsjail — P1 미구현, 이후 phase에서 추가 가능

    # 4) T3 fallback
    from ipe.sandbox.rlimit_runner import RlimitRunner
    if verbose:
        print(
            "⚠️  Falling back to T3 RlimitRunner — network/fs are NOT isolated. "
            "Install Docker Desktop or use --strict-sandbox to abort.",
            file=sys.stderr,
        )
    return RlimitRunner()
