"""Executor node — 3-Phase 결정론적 검증 엔진.

스펙: PROJECT_SPEC.md §4.5, ARCHITECTURE.md §3.9

본 P3 단계는 **최소 회로**:
- _normalize / _write_source / _compile / _execute_solution 헬퍼 (P3.2)
- Phase A skeleton: 단일 sample exact match (P3.3)

P4+에서 Phase A 3-way 휴리스틱, P5+에서 Phase B (adversarial + validator),
P6+에서 Phase C (generator stress + 병렬화), P7+에서 history/cost guard 추가.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from ipe.sandbox.runner import RunResult, RunSpec, SandboxedRunner
from ipe.state import ProblemState

# 정수 토큰 (음수 포함) — Phase B syntactic validator에서 사용
_INT_RE = re.compile(r"-?\d+")
MAX_INPUT_BYTES = 200  # adversarial input 길이 상한 (SPEC §4.3)

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
        # Phase A 통과 → Phase B 진입 (P5.3)
        return _run_phase_b(
            state=state,
            results=results,
            samples=samples,
            run_dir=run_dir,
            runner=runner,
            language=language,
            time_limit=time_limit,
            memory_limit=memory_limit,
            next_iter=next_iter,
        )

    # P4 — Phase A 3-way 휴리스틱 라우팅 (REVIEW W3)
    target = _decide_phase_a_route(results)
    feedback_msg = _build_phase_a_feedback(results, target)
    return {
        **state,
        "iteration_count": next_iter,
        "execution_results": results,
        "last_failed_node": target,
        "feedback_message": feedback_msg,
    }


def _run_phase_b(
    *,
    state: ProblemState,
    results: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    run_dir: Path,
    runner: SandboxedRunner,
    language: str,
    time_limit: int,
    memory_limit: int,
    next_iter: int,
) -> ProblemState:
    """Phase B — adversarial inputs 검증 (P5.3).

    각 adversarial input에 대해:
    1. ``_validate_input_against_constraints``로 syntactic 검증
       위반 시 → auditor 책임 (validator failure로 카운트, results 미추가)
    2. validator 통과한 input은 솔루션 실행
       OK → ``testcases``에 ``{kind: "adversarial", expected_output: <actual>, ...}`` 추가
       RTE/TLE/MLE → coder 책임 (execution failure로 카운트)

    Phase B 라우팅:
    - adversarial 부재 → auditor (산출물 누락)
    - validator 실패가 우세 → auditor
    - execution 실패가 우세 → coder
    - 모두 통과 → ``final_status="success"`` (P6에서 Phase C 추가 시 변경)
    """
    adversarial = state.get("adversarial_inputs") or []
    if not adversarial:
        return {
            **state,
            "iteration_count": next_iter,
            "execution_results": results,
            "last_failed_node": "auditor",
            "feedback_message": "no adversarial_inputs (auditor must generate)",
        }

    cs = state.get("constraints_structured")
    validator_fail_count = 0
    execution_fail_count = 0
    oracle_added: list[dict[str, Any]] = []

    for idx, tc in enumerate(adversarial):
        inp = str(tc.get("input", ""))
        err = _validate_input_against_constraints(inp, cs)
        if err is not None:
            validator_fail_count += 1
            # validator 실패는 실행 안 했으므로 results에 추가 안 함 — 별도 카운트만
            continue

        out = _execute_solution(
            runner,
            run_dir,
            language,
            inp,
            time_limit_ms=time_limit,
            memory_limit_mb=memory_limit,
        )
        actual = _normalize(out.stdout)
        passed = out.status == "OK"
        results.append({
            "phase": "adversarial",
            "index": idx,
            "pass": passed,
            "status": out.status,
            "execution_time_ms": out.elapsed_ms,
            "input": inp,
            "actual": actual,
            "stderr": out.stderr,
        })
        if passed:
            oracle_added.append({
                "kind": "adversarial",
                "input": inp,
                "expected_output": actual,
                "category": str(tc.get("category", "ADVERSARIAL")),
                "reason": str(tc.get("reason", "")),
                "execution_time_ms": out.elapsed_ms,
            })
        else:
            execution_fail_count += 1

    # 라우팅
    if validator_fail_count > 0 or execution_fail_count > 0:
        if validator_fail_count > execution_fail_count:
            target = "auditor"
            msg = (
                f"phase B: {validator_fail_count} adversarial inputs violate "
                f"constraints (auditor must regenerate)"
            )
        else:
            target = "coder"
            msg = (
                f"phase B: solution failed on {execution_fail_count} "
                f"adversarial cases (RTE/TLE/MLE)"
            )
        return {
            **state,
            "iteration_count": next_iter,
            "execution_results": results,
            "last_failed_node": target,
            "feedback_message": msg,
        }

    # 모두 통과 — testcases 누적 후 success (P6에서 Phase C 추가)
    sample_with_kind = [{**s, "kind": "sample"} for s in samples]
    all_testcases = sample_with_kind + oracle_added

    return {
        **state,
        "iteration_count": next_iter,
        "execution_results": results,
        "testcases": all_testcases,
        "final_status": "success",
        "last_failed_node": None,
        "feedback_message": None,
    }


def _decide_phase_a_route(results: list[dict[str, Any]]) -> str:
    """Phase A failure 결과로부터 라우팅 결정.

    - (a) 다수 통과 + 소수 실패 + 크래시 없음 → architect (sample expected_output 의심)
    - (b) 전체 실패 + 컴파일 OK + 모든 sample이 OK 상태 + 출력이 모두 unique
          → architect (sample 전체가 잘못되었을 가능성, REVIEW W3 신규 분기)
    - (c) else (다수 실패 + 크래시 동반 또는 출력 패턴 불일관) → coder

    sample 1개일 때 unique check는 자동 충족 (vacuously true)되므로,
    분기 (b)는 ``n_total >= 2``인 경우에만 적용한다.
    """
    n_total = len(results)
    if n_total == 0:
        return "coder"

    n_pass = sum(1 for r in results if r["pass"])
    has_crash = any(r["status"] in ("RTE", "TLE", "MLE") for r in results)

    # (a) 다수 통과 + 소수 실패 + 크래시 없음
    if 0 < n_pass < n_total and not has_crash:
        return "architect"

    # (b) 전체 실패 + 컴파일 OK + 일관된 unique 출력 (>=2 samples)
    all_ok = all(r["status"] == "OK" for r in results)
    unique_outputs = len({r["actual"] for r in results}) == n_total
    if n_pass == 0 and all_ok and unique_outputs and n_total >= 2:
        return "architect"

    # (c) 그 외 — 솔루션 버그 의심
    return "coder"


def _build_phase_a_feedback(results: list[dict[str, Any]], target: str) -> str:
    n_total = len(results)
    n_pass = sum(1 for r in results if r["pass"])
    failures = n_total - n_pass
    if target == "architect" and n_pass > 0:
        return (
            f"phase A: {n_pass}/{n_total} passed but {failures} mismatched "
            f"(sample expected_output likely wrong)"
        )
    if target == "architect":
        return (
            f"phase A: all {n_total} failed but solution gave consistent unique "
            f"outputs (samples likely wrong)"
        )
    return f"phase A failures: {failures}/{n_total}"
