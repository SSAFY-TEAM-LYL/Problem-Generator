"""Executor Phase B/C 본체 — adversarial 검증 + generator stress.

스펙: PROJECT_SPEC.md §4.5, ARCHITECTURE.md §3.9 (Phase B/C)
근거: IMPLEMENTATION_ROADMAP §6 risk note — executor.py 라인 budget(≤620)
초과 회피를 위한 분리.

함수:
- ``_run_phase_b``: adversarial inputs → syntactic validator + 솔루션 실행
- ``_run_phase_c``: (generator × seed) 병렬 stress + 정해 성능 게이트(P6.4)
- ``_build_failure_feedback``: fail case 첫 N개의 detail을 prompt-friendly
  텍스트로 빌드 (R1 — Coder/Auditor가 abstract count만 받지 않도록)
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

# R1: feedback에 포함할 fail case 최대 개수 (token 비용 cap).
# 너무 많으면 Coder context 낭비 / 너무 적으면 진단 정보 부족 — 3이 균형점.
_MAX_FAILURE_DETAILS = 3
# 각 fail case의 stderr/input excerpt 길이 cap.
_EXCERPT_CHARS = 200
# R11 (Sprint 1.5): Coder가 받는 feedback의 input_bytes가 이 임계값 이상이면
# 명시적 buffered-IO 경고를 prompt에 삽입. 근거: e2e Run 3 Two Sum이 1.97MB
# stress input에서 RTE — Coder가 input size를 "input_bytes=1977874" 숫자로
# 보고도 IO 최적화 자발적 떠올리지 못함. 1MB는 typical 알고리즘 문제에서
# default IO로 처리 가능한 경계점.
_HIGH_VOLUME_INPUT_BYTES = 1_000_000


def _excerpt(s: str | None, *, limit: int = _EXCERPT_CHARS) -> str:
    """문자열을 limit 길이로 잘라 prompt-friendly form으로 반환.

    None/빈 문자열 → ``""``. 잘림 시 ``...`` 접미사.
    """
    if not s:
        return ""
    s = s.replace("\r\n", "\n")
    if len(s) <= limit:
        return s
    return s[:limit] + "..."


def _build_failure_feedback(
    *,
    header: str,
    failures: list[dict[str, Any]],
    role: str,
) -> str:
    """fail case 첫 N개의 구체 정보를 prompt-friendly 텍스트로 빌드.

    R1 fix — Coder/Auditor가 ``"phase X: N cases failed"``만 받던 abstract
    feedback 구조를 보강. 각 case의 status / stderr / input excerpt를 노출해
    LLM이 "어디서 어떻게 실패했는가"를 직접 볼 수 있게 한다.

    args:
        header: 한 줄 요약 ("phase C: solution failed on 4 stress cases ...")
        failures: ``execution_results`` 항목들 (phase B/C 둘 다 동일 schema)
        role: ``"coder"`` / ``"auditor"`` / ``"generator"`` — 어떤 노드가
            이 feedback을 받게 될지 (Coder는 stderr 위주, Auditor는 violated
            input 위주로 가이드)

    returns:
        header + 각 fail case detail (최대 ``_MAX_FAILURE_DETAILS``개)을
        포함하는 multi-line 문자열.
    """
    if not failures:
        return header

    lines = [header]
    shown = failures[:_MAX_FAILURE_DETAILS]
    if role == "coder":
        # R11: high-volume input 감지 시 buffered-IO 사용 명시 경고. Coder가
        # input_bytes 숫자만 보고는 "이 정도면 IO 최적화 필요"를 자발적으로
        # 떠올리지 못함 (e2e Run 3 검증). 임계값 초과 case 1개라도 있으면
        # 명시적 가이드를 prompt 상단에 주입한다.
        max_input_bytes = max(
            (int(f.get("input_bytes") or 0) for f in failures), default=0
        )
        if max_input_bytes >= _HIGH_VOLUME_INPUT_BYTES:
            mb = max_input_bytes / 1_000_000
            lines.append(
                f"\n⚠️  HIGH-VOLUME INPUT detected (max {mb:.2f} MB). "
                "Default line-by-line IO will TLE/RTE — switch to buffered IO:"
            )
            lines.append("  - Python: `data = sys.stdin.buffer.read().split()`")
            lines.append("  - Java:   BufferedReader + StreamTokenizer")
            lines.append("  - Output: collect into list, then sys.stdout.write")
        lines.append(f"\nFailing cases (first {len(shown)}):")
        for i, f in enumerate(shown, 1):
            phase = f.get("phase", "?")
            status = f.get("status", "?")
            elapsed = f.get("execution_time_ms", 0)
            stderr = _excerpt(f.get("stderr"))
            inp = _excerpt(f.get("input") or f.get("stdin_text"))
            inp_bytes = f.get("input_bytes")
            gen = f.get("generator")
            seed = f.get("seed")
            ident_parts = [f"phase={phase}", f"status={status}", f"elapsed_ms={elapsed}"]
            if gen is not None:
                ident_parts.append(f"generator={gen}")
            if seed is not None:
                ident_parts.append(f"seed={seed}")
            if inp_bytes is not None:
                ident_parts.append(f"input_bytes={inp_bytes}")
            lines.append(f"  {i}. " + " ".join(ident_parts))
            if stderr:
                lines.append(f"     stderr: {stderr!r}")
            if inp:
                lines.append(f"     input: {inp!r}")
    elif role == "auditor":
        lines.append(f"\nViolating adversarial inputs (first {len(shown)}):")
        for i, f in enumerate(shown, 1):
            inp = _excerpt(f.get("input"))
            reason = f.get("validator_error") or "constraint violated"
            lines.append(f"  {i}. reason={reason!r}")
            if inp:
                lines.append(f"     input: {inp!r}")
    else:  # generator
        lines.append(f"\nFailing generator scripts (first {len(shown)}):")
        for i, f in enumerate(shown, 1):
            gen = f.get("generator", "?")
            seed = f.get("seed", "?")
            err = _excerpt(f.get("stderr"))
            lines.append(f"  {i}. generator={gen} seed={seed}")
            if err:
                lines.append(f"     error: {err!r}")
    return "\n".join(lines)


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
    validator_failures: list[dict[str, Any]] = []
    execution_failures: list[dict[str, Any]] = []
    oracle_added: list[dict[str, Any]] = []

    for idx, tc in enumerate(adversarial):
        inp = str(tc.get("input", ""))
        err = _validate_input_against_constraints(inp, cs)
        if err is not None:
            # validator 실패는 실행 안 했으므로 results에 추가 안 함 — fail
            # 메타데이터만 별도 보존하여 R1 detailed feedback에 활용.
            validator_failures.append({
                "phase": "adversarial",
                "index": idx,
                "input": inp,
                "validator_error": err,
            })
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
        rec = {
            "phase": "adversarial",
            "index": idx,
            "pass": passed,
            "status": out.status,
            "execution_time_ms": out.elapsed_ms,
            "input": inp,
            "actual": actual,
            "stderr": out.stderr,
        }
        results.append(rec)
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
            execution_failures.append(rec)

    # 라우팅 — R1: header + 첫 N case의 detail을 함께 포함
    validator_fail_count = len(validator_failures)
    execution_fail_count = len(execution_failures)
    if validator_fail_count > 0 or execution_fail_count > 0:
        if validator_fail_count > execution_fail_count:
            target = "auditor"
            header = (
                f"phase B: {validator_fail_count} adversarial inputs violate "
                f"constraints (auditor must regenerate)"
            )
            msg = _build_failure_feedback(
                header=header, failures=validator_failures, role="auditor",
            )
        else:
            target = "coder"
            header = (
                f"phase B: solution failed on {execution_fail_count} "
                f"adversarial cases (RTE/TLE/MLE)"
            )
            msg = _build_failure_feedback(
                header=header, failures=execution_failures, role="coder",
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

    # 결과 수집 + 분류 — R1: fail 항목을 detail까지 보존
    generator_failures: list[dict[str, Any]] = []
    solution_failures: list[dict[str, Any]] = []
    stress_oracle: list[dict[str, Any]] = []

    for cr in completed:
        if cr["kind"] == "gen_fail":
            rec = {
                "phase": "stress",
                "generator": cr["generator"],
                "seed": cr["seed"],
                "pass": False,
                "status": "GENERATOR_FAIL",
                "execution_time_ms": 0,
                "stderr": cr["error"],
            }
            results.append(rec)
            generator_failures.append(rec)
        else:
            out = cr["out"]
            actual = cr["actual"]
            stdin_text = cr["stdin_text"]
            passed = out.status == "OK"
            rec = {
                "phase": "stress",
                "generator": cr["generator"],
                "seed": cr["seed"],
                "pass": passed,
                "status": out.status,
                "execution_time_ms": out.elapsed_ms,
                "input_bytes": len(stdin_text),
                "output_bytes": len(actual),
                "stderr": out.stderr,
                # R1: Coder가 첫 N개 fail의 input을 직접 볼 수 있도록 보존.
                # token 비용 cap은 _build_failure_feedback에서 _excerpt가 처리.
                "stdin_text": stdin_text,
            }
            results.append(rec)
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
                solution_failures.append(rec)

    # 라우팅 — R1: header + 첫 N case의 detail을 함께 포함
    generator_fail_count = len(generator_failures)
    solution_fail_count = len(solution_failures)
    if generator_fail_count > 0 or solution_fail_count > 0:
        if generator_fail_count > solution_fail_count:
            target = "generator"
            header = (
                f"phase C: {generator_fail_count} generator scripts failed "
                f"(generator must regenerate)"
            )
            msg = _build_failure_feedback(
                header=header, failures=generator_failures, role="generator",
            )
        else:
            target = "coder"
            header = (
                f"phase C: solution failed on {solution_fail_count} stress "
                f"cases (RTE/TLE/MLE)"
            )
            msg = _build_failure_feedback(
                header=header, failures=solution_failures, role="coder",
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
