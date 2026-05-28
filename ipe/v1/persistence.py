"""outputs/ persistence — V1State 의 spec/design/attempt/verification 영속화.

P3 §69. portfolio + catalog browsing + future option C / RCA 분석 base.

각 run 은 ``outputs/<run_id>/`` 디렉토리에 5개 file:
- ``spec.json``         : ProblemSpec (title/description/constraints/io/samples)
- ``design.json``       : AlgorithmDesign (algorithm_name/pseudocode/invariants)
- ``attempt.py``        : SolutionAttempt.code (raw Python)
- ``verification.json`` : VerificationResult (sample_results/violations/feedback)
- ``outcome.json``      : 요약 metric (final_status/sample_pass_count/...)

기존 jsonl (RunOutcome) 와 보완 — jsonl 은 batch metric, outputs/ 는 단일 run
full artifact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .state import V1State


@dataclass(frozen=True)
class PersistedPaths:
    """저장된 file 들의 절대 경로 (caller 가 user 에게 표시용)."""

    run_dir: Path
    spec_json: Path | None
    design_json: Path | None
    attempt_py: Path | None
    verification_json: Path | None
    outcome_json: Path
    problem_md: Path | None  # 사람용 markdown 문제 지문
    samples_dir: Path | None  # samples/<i>.in + <i>.out 분리


def persist_run_outputs(
    state: V1State,
    output_dir: Path | str = "outputs",
) -> PersistedPaths:
    """V1State 의 (가능한) 모든 typed artifact 를 outputs/<run_id>/ 에 dump.

    None 인 필드 (e.g. fail 시 attempt 가 없음) 는 skip — 항상 outcome.json 은 dump.
    """
    base = Path(output_dir) / state.run_id
    base.mkdir(parents=True, exist_ok=True)

    spec_path: Path | None = None
    if state.spec is not None:
        spec_path = base / "spec.json"
        spec_path.write_text(
            state.spec.model_dump_json(indent=2), encoding="utf-8"
        )

    design_path: Path | None = None
    if state.design is not None:
        design_path = base / "design.json"
        design_path.write_text(
            state.design.model_dump_json(indent=2), encoding="utf-8"
        )

    attempt_path: Path | None = None
    if state.attempt is not None:
        attempt_path = base / "attempt.py"
        attempt_path.write_text(state.attempt.code, encoding="utf-8")

    verification_path: Path | None = None
    if state.verification is not None:
        verification_path = base / "verification.json"
        verification_path.write_text(
            state.verification.model_dump_json(indent=2), encoding="utf-8"
        )

    outcome = _build_outcome_summary(state)
    outcome_path = base / "outcome.json"
    outcome_path.write_text(
        json.dumps(outcome, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 사람용 문제 지문 (markdown) + samples 디렉토리 분리 (1.in/1.out ...)
    problem_md_path = _write_problem_md(state, base)
    samples_dir_path = _write_samples_dir(state, base)

    return PersistedPaths(
        run_dir=base.resolve(),
        spec_json=spec_path,
        design_json=design_path,
        attempt_py=attempt_path,
        verification_json=verification_path,
        outcome_json=outcome_path,
        problem_md=problem_md_path,
        samples_dir=samples_dir_path,
    )


def _write_problem_md(state: V1State, base: Path) -> Path | None:
    """spec → 사람 친화적 markdown problem statement.

    online judge / 문제집 표준 형식:
    - title heading
    - 본문 (description)
    - 입력/출력 형식
    - 제약사항 (constraint list)
    - 샘플 입출력
    """
    if state.spec is None:
        return None
    spec = state.spec
    lines: list[str] = [f"# {spec.title}", "", spec.description, ""]
    lines.extend(["## 입력", "", spec.io_contract.input_format, ""])
    lines.extend(["## 출력", "", spec.io_contract.output_format, ""])
    if spec.constraints:
        lines.append("## 제약사항")
        lines.append("")
        for c in spec.constraints:
            line = f"- `{c.min_value} <= {c.name} <= {c.max_value}`"
            if c.description:
                line += f" — {c.description}"
            lines.append(line)
        lines.append("")
    lines.extend(["## 샘플", ""])
    for i, s in enumerate(spec.sample_testcases, start=1):
        lines.append(f"### 샘플 {i}")
        lines.append("")
        if s.description:
            lines.append(f"_{s.description}_")
            lines.append("")
        lines.append("**입력:**")
        lines.append("```")
        lines.append(s.input_text.rstrip("\n"))
        lines.append("```")
        lines.append("")
        lines.append("**출력:**")
        lines.append("```")
        lines.append(s.expected_output.rstrip("\n"))
        lines.append("```")
        lines.append("")
    md_path = base / "problem.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def _write_samples_dir(state: V1State, base: Path) -> Path | None:
    """sample 별로 ``samples/<i>.in`` / ``<i>.out`` 분리 (1-indexed).

    online judge convention — ``diff <(python attempt.py < 1.in) 1.out`` 채점 가능.
    """
    if state.spec is None or not state.spec.sample_testcases:
        return None
    sdir = base / "samples"
    sdir.mkdir(exist_ok=True)
    for i, s in enumerate(state.spec.sample_testcases, start=1):
        (sdir / f"{i}.in").write_text(s.input_text, encoding="utf-8")
        (sdir / f"{i}.out").write_text(s.expected_output, encoding="utf-8")
    return sdir


def _build_outcome_summary(state: V1State) -> dict[str, object]:
    v = state.verification
    return {
        "run_id": state.run_id,
        "target_algorithm": state.target_algorithm.value,
        "final_status": state.final_status,
        "iteration_used": state.iteration,
        "max_iterations": state.max_iterations,
        "sample_pass_count": (
            sum(1 for sr in v.sample_results if sr.passed) if v else 0
        ),
        "sample_total": len(v.sample_results) if v else 0,
        "samples_engaged": v.samples_engaged if v else 0,
        "invariant_violations": (
            [iv.invariant_kind for iv in v.invariant_violations] if v else []
        ),
        "blocking_signatures": [
            r.blocking_signature for r in state.context.iterations
        ],
        "iteration_history": [
            r.model_dump(mode="json") for r in state.context.iterations
        ],
    }
