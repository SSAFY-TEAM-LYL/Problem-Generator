"""Executor node — 3-Phase 결정론적 검증 엔진.

스펙: PROJECT_SPEC.md §4.5, ARCHITECTURE.md §3.9

본 P3 단계는 **최소 회로**:
- _normalize / _write_source / _compile / _execute_solution 헬퍼 (P3.2)
- Phase A skeleton: 단일 sample exact match (P3.3)

P4+에서 Phase A 3-way 휴리스틱, P5+에서 Phase B (adversarial + validator),
P6+에서 Phase C (generator stress + 병렬화), P7+에서 history/cost guard 추가.
"""

from __future__ import annotations

from pathlib import Path

from ipe.sandbox.runner import RunResult, RunSpec, SandboxedRunner

DEFAULT_TIME_LIMIT_MS = 5000
DEFAULT_MEMORY_LIMIT_MB = 512
COMPILE_TIME_LIMIT_MS = 60000   # Java javac은 느릴 수 있음
COMPILE_MEMORY_LIMIT_MB = 1024


def _normalize(s: str) -> str:
    """stdout 비교용 정규화 — 줄 끝 공백 / Windows 개행 / 양 끝 공백 제거."""
    cleaned = s.replace("\r\n", "\n").strip()
    return "\n".join(line.rstrip() for line in cleaned.split("\n"))


def _write_source(run_dir: Path, language: str, code: str) -> Path:
    """solution_code를 적절한 파일명으로 저장.

    python → ``solution.py``
    java   → ``Solution.java`` (Java public class 명명 규칙)
    """
    if language == "python":
        path = run_dir / "solution.py"
    elif language == "java":
        path = run_dir / "Solution.java"
    else:
        raise ValueError(f"unsupported language: {language}")
    path.write_text(code, encoding="utf-8")
    return path


def _compile(
    runner: SandboxedRunner,
    run_dir: Path,
    language: str,
) -> tuple[bool, str]:
    """language별 컴파일. python은 no-op.

    Returns:
        ``(success, error_message)``. 실패 시 error_message는 stderr/stdout.
    """
    if language == "python":
        return True, ""
    if language == "java":
        spec = RunSpec(
            cmd=["javac", "Solution.java"],
            cwd=str(run_dir),
            time_limit_ms=COMPILE_TIME_LIMIT_MS,
            memory_limit_mb=COMPILE_MEMORY_LIMIT_MB,
        )
        res = runner.run(spec)
        if res.status != "OK":
            err = res.stderr or res.stdout or f"compile {res.status}"
            return False, err
        return True, ""
    raise ValueError(f"unsupported language: {language}")


def _run_cmd(language: str) -> list[str]:
    """언어별 실행 cmd. cwd는 caller(`run_dir`)에서 설정."""
    if language == "python":
        return ["python3", "solution.py"]
    if language == "java":
        return ["java", "-cp", ".", "Solution"]
    raise ValueError(f"unsupported language: {language}")


def _execute_solution(
    runner: SandboxedRunner,
    run_dir: Path,
    language: str,
    stdin_text: str,
    *,
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> RunResult:
    """컴파일된 솔루션을 stdin과 함께 실행."""
    spec = RunSpec(
        cmd=_run_cmd(language),
        cwd=str(run_dir),
        stdin=stdin_text,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
    )
    return runner.run(spec)
