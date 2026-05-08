"""Executor node — 3-Phase 결정론적 검증 엔진.

스펙: PROJECT_SPEC.md §4.5, ARCHITECTURE.md §3.9

본 P3 단계는 **최소 회로**:
- _normalize / _write_source / _compile / _execute_solution 헬퍼 (P3.2)
- Phase A skeleton: 단일 sample exact match (P3.3)

P4+에서 Phase A 3-way 휴리스틱, P5+에서 Phase B (adversarial + validator),
P6+에서 Phase C (generator stress + 병렬화), P7+에서 history/cost guard 추가.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ipe.sandbox.runner import RunResult, RunSpec, SandboxedRunner
from ipe.state import ProblemState

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


# ============================================================================
# Phase A skeleton (P3.3) — 단일 sample exact match
# P4에서 3-way 휴리스틱, P5/P6에서 Phase B/C 추가
# ============================================================================


def run(
    state: ProblemState,
    *,
    runner: SandboxedRunner,
    workdir_root: Path | None = None,
) -> ProblemState:
    """Executor 노드 — P3 단계는 컴파일 + Phase A skeleton만.

    1. workdir 생성, solution 작성, 컴파일 (실패 시 → coder)
    2. samples 누락 체크 (architect 라우팅)
    3. Phase A: 각 sample exact match
    4. 모두 통과 → ``final_status="success"`` (P5/P6에서 Phase B/C 추가 시 변경)
    5. 일부 실패 → coder (P4에서 3-way 휴리스틱)
    """
    language = state.get("target_language", "python")
    code = state.get("solution_code", "")
    samples = state.get("sample_testcases", [])
    next_iter = state.get("iteration_count", 0) + 1

    if not code:
        return {
            **state,
            "iteration_count": next_iter,
            "feedback_message": "no solution_code",
            "last_failed_node": "coder",
        }

    # workdir 생성
    workdir = workdir_root if workdir_root is not None else Path("workdir")
    workdir.mkdir(parents=True, exist_ok=True)
    run_dir = workdir / f"run_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir()

    _write_source(run_dir, language, code)
    ok, compile_err = _compile(runner, run_dir, language)
    if not ok:
        return {
            **state,
            "iteration_count": next_iter,
            "last_failed_node": "coder",
            "feedback_message": f"compile error:\n{compile_err}",
        }

    if not samples:
        return {
            **state,
            "iteration_count": next_iter,
            "last_failed_node": "architect",
            "feedback_message": "no sample_testcases",
        }

    # constraints_structured에서 problem-specific limit 적용 (없으면 default)
    cs = state.get("constraints_structured") or {}
    time_limit = int(cs.get("time_limit_ms", DEFAULT_TIME_LIMIT_MS))
    memory_limit = int(cs.get("memory_limit_mb", DEFAULT_MEMORY_LIMIT_MB))

    # Phase A — 각 sample exact match
    results: list[dict[str, Any]] = []
    failures = 0

    for idx, tc in enumerate(samples):
        stdin_text = str(tc.get("input", ""))
        expected = _normalize(str(tc.get("expected_output", "")))

        out = _execute_solution(
            runner,
            run_dir,
            language,
            stdin_text,
            time_limit_ms=time_limit,
            memory_limit_mb=memory_limit,
        )
        actual = _normalize(out.stdout)
        passed = out.status == "OK" and actual == expected
        if not passed:
            failures += 1

        results.append({
            "phase": "sample",
            "index": idx,
            "pass": passed,
            "status": out.status,
            "execution_time_ms": out.elapsed_ms,
            "expected": expected,
            "actual": actual,
            "stderr": out.stderr,
        })

    if failures == 0:
        # P3 단계 — Phase A 통과 = success (Phase B/C는 P5/P6에서 추가)
        return {
            **state,
            "iteration_count": next_iter,
            "execution_results": results,
            "final_status": "success",
            "last_failed_node": None,
            "feedback_message": None,
        }

    # 일부 실패 — P3 단계는 단순히 coder (P4에서 3-way 휴리스틱)
    return {
        **state,
        "iteration_count": next_iter,
        "execution_results": results,
        "last_failed_node": "coder",
        "feedback_message": f"phase A failures: {failures}/{len(samples)}",
    }
