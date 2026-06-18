"""canonical(v1) 산출 → v2 DB 적재 브리지.

v1 canonical 그래프(무합성·단일 알고리즘·직접 렌더 = '쉬운 문제')의 최종 ``V1State`` 를
v2 ``persist_run`` body{batch, final_status, package} 로 변환해 동일 DB(problems/
test_cases)에 멱등 적재한다. v1 ``ProblemSpec`` 하위 객체(ConstraintRange/SampleTestCase/
IOContract)가 v2 package 필드명과 일치 → 직접 매핑. ``test_suite`` 는 sample(3~5)을
case 로 사용한다(canonical 은 풀 채점셋 노드 없음 — M4 풀 채점셋은 v2 전용).

CLI::

    python -m ipe.v2.canonical_ingest --seeds two_sum,binary_search,sort \\
        --db-url <proxy-url> [--out outputs/canonical]
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ipe.v1.schema import TargetAlgorithm
from ipe.v1.state import V1State
from ipe.v2.db import persist_run
from ipe.v2.difficulty import AnthropicDifficultyLLM, annotate_difficulty

if TYPE_CHECKING:
    from ipe.v1.schema import TestSuite

_PACKAGE_VERSION = "canonical-1"


def canonical_body(
    final: V1State,
    *,
    run_id: str,
    seed: str,
    test_suite: TestSuite | None = None,
) -> dict[str, Any]:
    """V1State(canonical success) → ``persist_run`` body. spec/attempt 필수.

    v1 의 ProblemSpec/SolutionAttempt 가 v2 package 필드명과 일치하므로 직접 매핑.
    ``test_suite`` 가 주어지면(hybrid: ``expand_grading_suite`` 의 assembled 풀셋) 그것을
    채점셋으로 쓴다 — origin=golden_origin, timing=케이스별 golden_elapsed_ms 최대값.
    없으면 sample 을 case 로 승격(canonical 무합성·단일 알고리즘, sample 뿐).
    """
    if final.spec is None or final.attempt is None:
        msg = "canonical_body: spec/attempt 없는 미완 run (success 만 변환 가능)"
        raise ValueError(msg)
    spec = final.spec
    attempt = final.attempt
    samples = [s.model_dump() for s in spec.sample_testcases]
    if test_suite is not None:
        suite_cases = [
            {
                "input_text": c.input_text,
                "expected_output": c.expected_output,
                "category": c.category,
            }
            for c in test_suite.cases
        ]
        suite_origin = test_suite.golden_origin or "assembled"
        elapsed = [
            c.golden_elapsed_ms
            for c in test_suite.cases
            if c.golden_elapsed_ms is not None
        ]
    else:
        suite_cases = [
            {
                "input_text": s["input_text"],
                "expected_output": s["expected_output"],
                "category": "sample",
            }
            for s in samples
        ]
        suite_origin = "canonical_samples"
        elapsed = (
            [sr.elapsed_ms for sr in final.verification.sample_results]
            if final.verification is not None
            else []
        )
    timing: dict[str, Any] = (
        {"max_golden_elapsed_ms": max(elapsed)} if elapsed else {}
    )
    package: dict[str, Any] = {
        "problem": {
            "title": spec.title,
            "description": spec.description,
            "io_contract": {
                "input_format": spec.io_contract.input_format,
                "output_format": spec.io_contract.output_format,
            },
            "constraints": [c.model_dump() for c in spec.constraints],
            "sample_testcases": samples,
        },
        "solution": {"golden_code": attempt.code, "language": attempt.language},
        "test_suite": {
            "cases": suite_cases,
            "origin": suite_origin,
        },
        "meta": {
            "package_version": _PACKAGE_VERSION,
            "mode": "canonical",
            "hidden_algorithm": spec.target_algorithm.value,
            "composition": [],
            "domain": None,
            "golden_language": attempt.language,
            "qa": {},
            "timing": timing,
        },
    }
    return {
        "batch": {"run_id": run_id, "seed": seed, "mode": "canonical"},
        "final_status": final.final_status,
        "package": package,
    }


def _run_canonical(seed: TargetAlgorithm, run_id: str, *, max_iter: int) -> V1State:
    """v1 canonical 그래프 1회 실행 → 최종 V1State."""
    from ipe.v1.graph import build_graph
    from ipe.v1.state import initial_state

    graph = build_graph()  # default = canonical (RFC §10)
    raw = graph.invoke(initial_state(run_id, seed, max_iterations=max_iter))
    return raw if isinstance(raw, V1State) else V1State.model_validate(raw)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m ipe.v2.canonical_ingest",
        description="canonical(v1) 쉬운 문제 생성 → v2 DB 적재 브리지",
    )
    p.add_argument("--seeds", required=True, help="comma-sep (예: two_sum,sort)")
    p.add_argument("--runs-per-seed", type=int, default=1)
    p.add_argument("--max-iter", type=int, default=6)
    p.add_argument("--db-url", default=os.environ.get("IPE_ADMIN_DB_URL"))
    p.add_argument("--out", default=None, help="v2-body JSON dump 디렉토리(선택)")
    p.add_argument(
        "--with-difficulty",
        action="store_true",
        help="BOJ 티어 난이도(RFC R4) calibration 주석 (meta.difficulty + DB 컬럼)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    args = _build_parser().parse_args(argv)
    seeds = [TargetAlgorithm(s.strip()) for s in args.seeds.split(",") if s.strip()]

    engine = None
    if args.db_url:
        from sqlalchemy import create_engine

        engine = create_engine(args.db_url, pool_pre_ping=True)
    difficulty_llm = AnthropicDifficultyLLM() if args.with_difficulty else None
    out_dir = Path(args.out) if args.out else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    inserted = skipped = 0
    for seed in seeds:
        for _ in range(args.runs_per_seed):
            run_id = f"canon-{seed.value}-{uuid.uuid4().hex[:8]}"
            final = _run_canonical(seed, run_id, max_iter=args.max_iter)
            if final.final_status != "success":
                skipped += 1
                print(f"  [{seed.value:14}] {final.final_status} → skip")
                continue
            body = canonical_body(final, run_id=run_id, seed=seed.value)
            if difficulty_llm is not None:
                body = {
                    **body,
                    "package": annotate_difficulty(
                        body["package"], llm=difficulty_llm
                    ),
                }
            if out_dir is not None:
                (out_dir / f"{seed.value}_{run_id}.json").write_text(
                    json.dumps(body, ensure_ascii=False, indent=2)
                )
            if engine is not None:
                pid = persist_run(engine, body)
                if pid:
                    inserted += 1
                    print(f"  [{seed.value:14}] success → DB insert {pid}")
            else:
                print(f"  [{seed.value:14}] success (DB 미적재 — --db-url 없음)")
    print(f"\ncanonical 적재: insert {inserted} · skip {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
