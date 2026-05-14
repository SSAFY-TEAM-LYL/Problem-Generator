"""Executor 저수준 헬퍼 — sandbox 실행, 컴파일, 입력 검증.

스펙: PROJECT_SPEC.md §4.5, ARCHITECTURE.md §3.9

본 모듈은 ``executor.py``와 ``_executor_phases.py``에서 공유되는 저수준
유틸을 모아둔다. 순환 import 회피 + executor.py 라인 budget(≤620) 준수
목적 (IMPLEMENTATION_ROADMAP §2, §6).

함수:
- ``_normalize``: stdout 비교용 정규화
- ``_write_source``: 언어별 소스 파일명 결정
- ``_compile``: Java javac 등 빌드 단계 (Python no-op)
- ``_run_cmd``: 언어별 실행 cmd
- ``_execute_solution``: 솔루션 sandbox 실행
- ``_run_generator``: Phase C generator script 실행
- ``_validate_input_against_constraints``: Phase B syntactic validator

상수:
- ``DEFAULT_TIME_LIMIT_MS``, ``DEFAULT_MEMORY_LIMIT_MB``: Phase A/B 기본
- ``COMPILE_*``: javac compile 한도
- ``GENERATOR_*``, ``MAX_GENERATED_INPUT_BYTES``: Phase C generator 한도
- ``PHASE_C_WORKERS``, ``ORACLE_SPEED_RATIO``: Phase C 병렬화 + 정해 게이트
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ipe.sandbox.runner import RunResult, RunSpec, SandboxedRunner

# 정수 토큰 (음수 포함) — Phase B syntactic validator에서 사용
_INT_RE = re.compile(r"-?\d+")
MAX_INPUT_BYTES = 200  # adversarial input 길이 상한 (SPEC §4.3)

DEFAULT_TIME_LIMIT_MS = 5000
DEFAULT_MEMORY_LIMIT_MB = 512
COMPILE_TIME_LIMIT_MS = 60000   # Java javac은 느릴 수 있음
# javac은 JVM 위에서 동작 — 시작만으로도 1-2GB virtual memory 잡음.
# Linux RLIMIT_AS 1024MB는 borderline (OOM 빈번, CI ubuntu fail 재현).
# 4096MB로 ↑ — javac 안정 + 일반 알고리즘 컴파일에 충분. macOS Darwin은
# RLIMIT_AS 무시라 영향 0.
COMPILE_MEMORY_LIMIT_MB = 4096

# Phase C — generator script 실행 한도 (P6.2)
GENERATOR_TIMEOUT_MS = 10_000
GENERATOR_MEMORY_LIMIT_MB = 1024
# R10 (v0.2.0 Sprint 2): 5MB → 2MB. e2e Run 3에서 1.97MB stress가 RTE 유발 —
# 정상 알고리즘 stress (N=200000 + 적정 value range)는 1.6MB 내, outlier만
# 차단. truncated_stdout 시 generator로 라우팅 (재작성 강제).
MAX_GENERATED_INPUT_BYTES = 2 * 1024 * 1024  # 2 MB
PHASE_C_WORKERS = 4              # ThreadPoolExecutor 동시 실행 수
ORACLE_SPEED_RATIO = 0.5         # 정해 성능 게이트: max-stress ≤ time_limit × 0.5 (P6.4)


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


def _run_generator(
    runner: SandboxedRunner,
    gen_dir: Path,
    gen_name: str,
    seed: int,
) -> tuple[bool, str, str]:
    """generator script를 시드와 함께 실행하여 stdin 텍스트 생성 (P6.2).

    Returns:
        ``(success, stdin_text, error_message)``
        - success=True 시 stdin_text는 생성된 입력
        - success=False 시 error_message는 사유 (sandbox status, truncation 등)
    """
    spec = RunSpec(
        cmd=["python3", f"{gen_name}.py", str(seed)],
        cwd=str(gen_dir),
        time_limit_ms=GENERATOR_TIMEOUT_MS,
        memory_limit_mb=GENERATOR_MEMORY_LIMIT_MB,
        max_stdout_bytes=MAX_GENERATED_INPUT_BYTES,
    )
    res = runner.run(spec)
    if res.status != "OK":
        err_excerpt = (res.stderr or res.stdout or "")[:300]
        return (
            False,
            "",
            f"generator '{gen_name}' (seed={seed}) {res.status}: {err_excerpt}",
        )
    if res.truncated_stdout:
        return (
            False,
            "",
            f"generator '{gen_name}' output exceeds {MAX_GENERATED_INPUT_BYTES} bytes",
        )
    return True, res.stdout, ""


def _validate_input_against_constraints(
    input_text: str,
    constraints_structured: Any,
) -> str | None:
    """input이 ``constraints_structured``에 부합하는지 syntactic 검증.

    반환:
    - 위반 사유 문자열 (Auditor로 라우팅하기 위함)
    - 통과 시 ``None``

    검증 항목 (best-effort, ARCH §3.9.5 W3 보강):
    1. 빈 input 거부
    2. ``len(input_text) > MAX_INPUT_BYTES`` 거부
    3. ``constraints_structured.variables``가 정의되어 있으면 모든 정수
       토큰이 ``[min(mins), max(maxs)]`` union range 안에 있는지 확인.

    variables가 비어있거나 numeric 정보가 없으면 검증 정보 부재로 ``None``
    (통과)로 처리한다 — over-restriction을 피하기 위해.
    """
    if not input_text:
        return "empty input"
    if len(input_text) > MAX_INPUT_BYTES:
        return f"input too long ({len(input_text)} > {MAX_INPUT_BYTES} chars)"

    if not constraints_structured:
        return None

    variables = constraints_structured.get("variables")
    if not isinstance(variables, list) or not variables:
        return None

    mins: list[float] = []
    maxs: list[float] = []
    for v in variables:
        if not isinstance(v, dict):
            continue
        if isinstance(v.get("min"), (int, float)):
            mins.append(float(v["min"]))
        if isinstance(v.get("max"), (int, float)):
            maxs.append(float(v["max"]))

    if not mins or not maxs:
        return None

    overall_min = min(mins)
    overall_max = max(maxs)

    for tok in _INT_RE.findall(input_text):
        n = int(tok)
        if n < overall_min:
            return f"input value {n} below min {int(overall_min)}"
        if n > overall_max:
            return f"input value {n} above max {int(overall_max)}"

    return None
