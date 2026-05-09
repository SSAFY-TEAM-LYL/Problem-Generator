"""Executor Phase B/C 본체 — adversarial 검증 + generator stress.

스펙: PROJECT_SPEC.md §4.5, ARCHITECTURE.md §3.9 (Phase B/C)
근거: IMPLEMENTATION_ROADMAP §6 risk note — executor.py 라인 budget(≤620)
초과 회피를 위한 분리.

함수:
- ``_run_phase_b``: adversarial inputs → syntactic validator + 솔루션 실행
- ``_run_phase_c``: (generator × seed) 병렬 stress + 정해 성능 게이트(P6.4)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ipe.nodes._executor_helpers import (
    ORACLE_SPEED_RATIO,
    PHASE_C_WORKERS,
    _execute_solution,
    _normalize,
    _run_generator,
    _validate_input_against_constraints,
)
from ipe.sandbox.runner import SandboxedRunner
from ipe.state import ProblemState


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
    - 모두 통과 → Phase C 진입 (P6.3)
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

    # Phase B 모두 통과 → Phase C 진입 (P6.3)
    return _run_phase_c(
        state=state,
        results=results,
        samples=samples,
        adversarial_oracle=oracle_added,
        run_dir=run_dir,
        runner=runner,
        language=language,
        time_limit=time_limit,
        memory_limit=memory_limit,
        next_iter=next_iter,
    )


def _run_phase_c(
    *,
    state: ProblemState,
    results: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    adversarial_oracle: list[dict[str, Any]],
    run_dir: Path,
    runner: SandboxedRunner,
    language: str,
    time_limit: int,
    memory_limit: int,
    next_iter: int,
) -> ProblemState:
    """Phase C — generator stress 검증 + 정해 성능 게이트 (P6.3, P6.4).

    각 (generator, seed) 쌍에 대해:
    1. ``_run_generator``로 stdin 텍스트 생성
       generator script 자체 실패 → generator failure로 카운트
    2. 솔루션 실행
       OK → ``testcases``에 ``{kind: "generated", expected_output: <actual>, ...}`` 추가
       RTE/TLE/MLE → solution failure로 카운트

    ThreadPoolExecutor로 병렬 실행 (4 worker default — subprocess는 GIL 영향 없음).

    라우팅:
    - generators 부재 → 'generator' (산출물 누락)
    - generator failure 우세 → 'generator'
    - solution failure 우세 → 'coder'
    - 모두 통과 + 정해 성능 게이트 통과 → ``final_status='success'``

    P6.4 정해 성능 게이트:
    - max-stress wall_time이 ``time_limit × ORACLE_SPEED_RATIO`` 초과 →
      'coder' ('oracle slow' 시그널 — 정해를 더 빠르게 다시 작성 요청)
    """
    generators = state.get("generators") or []
    if not generators:
        return {
            **state,
            "iteration_count": next_iter,
            "execution_results": results,
            "last_failed_node": "generator",
            "feedback_message": "no generators (generator must produce)",
        }

    # generator 스크립트들을 disk에 write
    gen_dir = run_dir / "generators"
    gen_dir.mkdir(parents=True, exist_ok=True)
    for g in generators:
        (gen_dir / f"{g['name']}.py").write_text(g["code"], encoding="utf-8")

    # 모든 (gen, seed) tasks 수집
    tasks: list[tuple[dict[str, Any], int]] = []
    for g in generators:
        for seed in g.get("seeds") or []:
            tasks.append((g, int(seed)))

    if not tasks:
        return {
            **state,
            "iteration_count": next_iter,
            "execution_results": results,
            "last_failed_node": "generator",
            "feedback_message": "no seeds in any generator",
        }

    def _process(task: tuple[dict[str, Any], int]) -> dict[str, Any]:
        g, seed = task
        gen_ok, stdin_text, gen_err = _run_generator(runner, gen_dir, g["name"], seed)
        if not gen_ok:
            return {
                "kind": "gen_fail",
                "generator": g["name"],
                "seed": seed,
                "error": gen_err,
            }
        out = _execute_solution(
            runner, run_dir, language, stdin_text,
            time_limit_ms=time_limit, memory_limit_mb=memory_limit,
        )
        return {
            "kind": "exec",
            "generator": g["name"],
            "seed": seed,
            "stdin_text": stdin_text,
            "out": out,
            "actual": _normalize(out.stdout),
        }

    completed: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=PHASE_C_WORKERS) as pool:
        futures = [pool.submit(_process, t) for t in tasks]
        for fut in as_completed(futures):
            completed.append(fut.result())

    # 결과 수집 + 분류
    generator_fail_count = 0
    solution_fail_count = 0
    stress_oracle: list[dict[str, Any]] = []

    for cr in completed:
        if cr["kind"] == "gen_fail":
            generator_fail_count += 1
            results.append({
                "phase": "stress",
                "generator": cr["generator"],
                "seed": cr["seed"],
                "pass": False,
                "status": "GENERATOR_FAIL",
                "execution_time_ms": 0,
                "stderr": cr["error"],
            })
        else:
            out = cr["out"]
            actual = cr["actual"]
            stdin_text = cr["stdin_text"]
            passed = out.status == "OK"
            results.append({
                "phase": "stress",
                "generator": cr["generator"],
                "seed": cr["seed"],
                "pass": passed,
                "status": out.status,
                "execution_time_ms": out.elapsed_ms,
                "input_bytes": len(stdin_text),
                "output_bytes": len(actual),
                "stderr": out.stderr,
            })
            if passed:
                stress_oracle.append({
                    "kind": "generated",
                    "generator": cr["generator"],
                    "seed": cr["seed"],
                    "input": stdin_text,
                    "expected_output": actual,
                    "execution_time_ms": out.elapsed_ms,
                })
            else:
                solution_fail_count += 1

    # 라우팅
    if generator_fail_count > 0 or solution_fail_count > 0:
        if generator_fail_count > solution_fail_count:
            target = "generator"
            msg = (
                f"phase C: {generator_fail_count} generator scripts failed "
                f"(generator must regenerate)"
            )
        else:
            target = "coder"
            msg = (
                f"phase C: solution failed on {solution_fail_count} stress "
                f"cases (RTE/TLE/MLE)"
            )
        return {
            **state,
            "iteration_count": next_iter,
            "execution_results": results,
            "last_failed_node": target,
            "feedback_message": msg,
        }

    # P6.4 정해 성능 게이트 — max-stress wall_time이 time_limit × 0.5 초과 시 coder
    if stress_oracle:
        max_stress_elapsed = max(o["execution_time_ms"] for o in stress_oracle)
        threshold = int(time_limit * ORACLE_SPEED_RATIO)
        if max_stress_elapsed > threshold:
            return {
                **state,
                "iteration_count": next_iter,
                "execution_results": results,
                "last_failed_node": "coder",
                "feedback_message": (
                    f"oracle slow: max-stress wall_time {max_stress_elapsed}ms > "
                    f"{threshold}ms (50% of time_limit_ms={time_limit})"
                ),
            }

    # 모두 통과 + 정해 성능 OK → success
    sample_with_kind = [{**s, "kind": "sample"} for s in samples]
    all_testcases = sample_with_kind + adversarial_oracle + stress_oracle

    return {
        **state,
        "iteration_count": next_iter,
        "execution_results": results,
        "testcases": all_testcases,
        "final_status": "success",
        "last_failed_node": None,
        "feedback_message": None,
    }
