"""CLI smoke 테스트 (polish round P-3) — A5/C3 해소.

스펙: ARCHITECTURE.md §3.1, IMPLEMENTATION_ROADMAP §1 P12.1
범위:
- ``python -m ipe.sandbox --tier <X>`` (A5: sandbox/__main__.py CLI)
- ``python main.py --help`` 및 빠른 exit path (C3: main.py 진입점)

실제 LLM 호출은 안 함 — subprocess CLI invocation만. 본 테스트는 통합 디렉토리에
있지만 외부 의존(ANTHROPIC_API_KEY)은 필요 없음.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _run(
    cmd: list[str], *, cwd: Path | None = None, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    """subprocess.run 래퍼 — 표준 환경에서 빠르게 실행 + capture."""
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout,
    )


# =============================================================================
# A5 — ipe.sandbox CLI selftest
# =============================================================================


class TestSandboxCli:
    def test_sandbox_main_rlimit_runs_and_emits_report(self) -> None:
        """python -m ipe.sandbox --tier rlimit → CLI 동작 + isolation JSON 출력.

        rlimit(T3)은 POSIX resource limit만 적용 — network/fs/memory 일부 차단 못 함.
        그래서 returncode는 0 또는 1 (isolation 일부 fail) 모두 valid. 핵심은
        CLI가 동작하고 isolation 결과를 stdout에 출력하는 것.
        """
        proj = Path(__file__).resolve().parents[2]
        result = _run(
            [sys.executable, "-m", "ipe.sandbox", "--tier", "rlimit"],
            cwd=proj,
        )
        # CLI가 동작 (segfault나 import error는 returncode > 1)
        assert result.returncode in (0, 1), (
            f"unexpected returncode={result.returncode}, "
            f"stderr={result.stderr!r}"
        )
        out = result.stdout + result.stderr
        # tier 정보 + isolation 결과 dict 키 출력 확인
        assert "T3" in out or "rlimit" in out.lower()
        assert "isolation" in out.lower() or "network" in out.lower()

    def test_sandbox_main_invalid_tier_returns_nonzero(self) -> None:
        """잘못된 tier → argparse error → exit code != 0."""
        proj = Path(__file__).resolve().parents[2]
        result = _run(
            [sys.executable, "-m", "ipe.sandbox", "--tier", "bogus_tier"],
            cwd=proj,
        )
        assert result.returncode != 0


# =============================================================================
# C3 — main.py CLI 진입점 (LLM 호출 없는 빠른 path만)
# =============================================================================


class TestMainCli:
    def test_main_help_returns_zero(self) -> None:
        """python main.py --help → argparse가 0 반환 (LLM 호출 없음)."""
        proj = Path(__file__).resolve().parents[2]
        result = _run([sys.executable, "main.py", "--help"], cwd=proj)
        assert result.returncode == 0
        # help 텍스트에 핵심 플래그 포함
        for flag in ("--algorithm", "--resume", "--replay", "--max-iter",
                     "--max-cost-usd", "--sandbox", "--budget-coder",
                     "--exec-workers"):
            assert flag in result.stdout, f"--help missing {flag}"

    def test_main_no_algorithm_fails(self) -> None:
        """algorithm/resume/replay 모두 없으면 argparse error → exit != 0."""
        proj = Path(__file__).resolve().parents[2]
        result = _run([sys.executable, "main.py"], cwd=proj)
        assert result.returncode != 0
        assert "--algorithm is required" in (result.stderr + result.stdout)

    def test_main_resume_missing_run_returns_2(self) -> None:
        """--resume <missing> → run_dir not found → exit 2."""
        proj = Path(__file__).resolve().parents[2]
        result = _run(
            [sys.executable, "main.py", "--resume", "no_such_run_xyz"],
            cwd=proj,
        )
        assert result.returncode == 2
        assert "not found" in (result.stderr + result.stdout)

    def test_main_resume_and_replay_mutually_exclusive(self) -> None:
        """--resume X --replay Y → argparse error → exit != 0."""
        proj = Path(__file__).resolve().parents[2]
        result = _run(
            [sys.executable, "main.py", "--resume", "x", "--replay", "y"],
            cwd=proj,
        )
        assert result.returncode != 0
        assert "mutually exclusive" in (result.stderr + result.stdout)


@pytest.mark.parametrize("flag,expected_in_help", [
    ("--algorithm", "target algorithm"),
    ("--language", "python,java"),
    ("--budget-architect", "BUDGET_ARCHITECT"),
    ("--exec-workers", "Phase C"),
])
def test_main_help_includes_expected_strings(
    flag: str, expected_in_help: str
) -> None:
    """주요 플래그의 metavar/help 문자열이 --help 출력에 포함."""
    proj = Path(__file__).resolve().parents[2]
    result = _run([sys.executable, "main.py", "--help"], cwd=proj)
    assert result.returncode == 0
    assert flag in result.stdout
    assert expected_in_help in result.stdout
