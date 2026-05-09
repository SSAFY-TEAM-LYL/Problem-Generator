"""Executor node — 3-Phase 결정론적 검증 엔진.

스펙: PROJECT_SPEC.md §4.5, ARCHITECTURE.md §3.9

본 모듈은 Phase A (sample exact match + 3-way 휴리스틱 라우팅)와
오케스트레이션을 담당한다. 저수준 헬퍼는 ``_executor_helpers.py``,
Phase B/C 본체는 ``_executor_phases.py``에 분리되어 있다
(IMPLEMENTATION_ROADMAP §2 라인 budget ≤620 준수, §6 risk note 참조).

흐름:
1. workdir 생성, solution 작성, 컴파일 (실패 → coder)
2. samples 누락 체크 (architect 라우팅)
3. Phase A: 각 sample exact match
4. Phase A 통과 → Phase B (P5.3) → Phase C (P6.3)
5. Phase A 일부 실패 → 3-way 라우팅 (P4)
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ipe.nodes._executor_helpers import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIME_LIMIT_MS,
    _compile,
    _execute_solution,
    _normalize,
    _write_source,
)
from ipe.nodes._executor_phases import _run_phase_b
from ipe.sandbox.runner import SandboxedRunner
from ipe.state import ProblemState


def run(
    state: ProblemState,
    *,
    runner: SandboxedRunner,
    workdir_root: Path | None = None,
) -> ProblemState:
    """Executor 노드 — 3-Phase 검증 오케스트레이션.

    1. workdir 생성, solution 작성, 컴파일 (실패 시 → coder)
    2. samples 누락 체크 (architect 라우팅)
    3. Phase A: 각 sample exact match
    4. 모두 통과 → Phase B (``_run_phase_b``) → Phase C
    5. 일부 실패 → 3-way 라우팅 (architect / coder)
    """
    language = state.get("target_language", "python")
    code = state.get("solution_code", "")
    samples = state.get("sample_testcases", [])
    next_iter = state.get("iteration_count", 0) + 1

    if not code:
        # Coder가 IMPOSSIBLE 선언 시 last_failed_node를 이미 set (예: "architect").
        # 그 라우팅 시그널을 덮어쓰지 않고 보존 — graph의 decision 노드가 처리.
        existing = state.get("last_failed_node")
        if existing and existing != "coder":
            return {**state, "iteration_count": next_iter}
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
