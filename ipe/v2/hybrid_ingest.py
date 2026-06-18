"""하이브리드 생성 파이프라인 — v1 생성방식 + v2 검증방식의 장점 결합.

v1 full 모드(단일 알고리즘 직접 생성 + golden↔brute differential reconcile)로 '쉬운
문제 + 정해 정합성'을 만들고, v2 QA 4-charter 게이트로 모호성(예: two_sum 비유일 정답)
까지 잡는다. golden↔brute 일치 **그리고** QA 통과한 것만 v2 DB 에 적재.

``canonical_ingest``(단일 golden·무검증)의 후속 — '장점만 취한' 결합:
- v1 생성: 무합성·단일 알고리즘 직접 = 진짜 쉬운 문제 (v2 strategist 는 항상 합성→하드)
- v2 검증: golden↔brute differential(정해버그) + QA ambiguity(비유일/모호) 게이트

CLI::

    python -m ipe.v2.hybrid_ingest --seeds two_sum,binary_search,sort \\
        [--db-url <proxy>] [--out outputs/hybrid] [--runs-per-seed 1]
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ipe.v1.schema import (
    ConstraintRange,
    GeneratedTestCase,
    IOContract,
    Narrative,
    ProblemSpec,
    QAReport,
    QAReview,
    QAReviewerKind,
    SampleTestCase,
    TargetAlgorithm,
    TestSuite,
)
from ipe.v1.state import V1State
from ipe.v2.canonical_ingest import canonical_body
from ipe.v2.db import persist_run
from ipe.v2.difficulty import AnthropicDifficultyLLM, annotate_difficulty
from ipe.v2.grading_expand import (
    AnthropicGradingInputGeneratorLLM,
    GradingInputGeneratorLLM,
    expand_grading_suite,
)
from ipe.v2.nodes.qa_reviewer import AnthropicQAReviewerLLM, QAReviewerLLM
from ipe.v2.state import V2State, initial_v2_state

if TYPE_CHECKING:
    from ipe.v1.verification._exec import CodeRunner

GOLDEN_MODEL = "claude-opus-4-8"
BRUTE_MODEL = "claude-sonnet-4-6"  # golden 과 distinct → 독립 differential
_QA_KINDS: tuple[QAReviewerKind, ...] = (
    "ambiguity",
    "fairness",
    "leakage",
    "difficulty",
)
# easy/B2C 문제용 QA charter (실측 근거). leakage 는 고전 문제(sort/two_sum)를 본질적으로
# '유출'로 reject = B2B 은닉 전용 우려라 제외. difficulty 는 '채점셋이 sample 뿐 →
# 하드코딩 가능'을 지적 = 빈약 TC 문제이며 풀 채점셋(후속) 도입 전까지 제외. ambiguity
# (정합성·비유일)·fairness(숨은 전제)만 출하 게이트 — 깨끗한 문제는 통과, 진짜 모호성은 잡힘.
_EASY_CHARTERS: tuple[QAReviewerKind, ...] = ("ambiguity", "fairness")


def _run_v1_full(seed: TargetAlgorithm, run_id: str, *, max_iter: int) -> V1State:
    """v1 full 모드 — architect 생성 + golden↔brute differential(distinct 모델 독립)."""
    from ipe.v1.graph import build_graph
    from ipe.v1.nodes import AnthropicCoderLLM
    from ipe.v1.state import initial_state

    graph = build_graph(
        mode="full",
        golden_llms=[AnthropicCoderLLM(GOLDEN_MODEL, parse_discipline=True)],
        brute_llm=AnthropicCoderLLM(BRUTE_MODEL, parse_discipline=True),
    )
    raw = graph.invoke(initial_state(run_id, seed, max_iterations=max_iter))
    return raw if isinstance(raw, V1State) else V1State.model_validate(raw)


def _qa_state(body: dict[str, Any], run_id: str) -> V2State:
    """body(package) → QA 리뷰용 최소 V2State (spec/narrative/test_suite)."""
    pkg = body["package"]
    prob = pkg["problem"]
    io = prob.get("io_contract") or {}
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm(pkg["meta"]["hidden_algorithm"]),
        title=prob.get("title", ""),
        description=prob.get("description", ""),
        io_contract=IOContract(
            input_format=io.get("input_format", ""),
            output_format=io.get("output_format", ""),
        ),
        constraints=[
            ConstraintRange(**c)
            for c in (prob.get("constraints") or [])
            if isinstance(c, dict)
        ],
        sample_testcases=[
            SampleTestCase(
                input_text=s.get("input_text", ""),
                expected_output=s.get("expected_output", ""),
            )
            for s in (prob.get("sample_testcases") or [])
            if isinstance(s, dict)
        ],
    )
    suite = TestSuite(
        cases=tuple(
            GeneratedTestCase(
                input_text=c.get("input_text", ""),
                expected_output=c.get("expected_output", ""),
                category=str(c.get("category") or ""),
            )
            for c in ((pkg.get("test_suite") or {}).get("cases") or ())
        )
    )
    # canonical/hybrid 은 직접 렌더(도메인 은닉 없음) — domain 은 nominal(min_length=1)
    narrative = Narrative(scenario=spec.description, hidden=False, domain="general")
    base = initial_v2_state(run_id, spec.target_algorithm)
    return base.model_copy(
        update={"spec": spec, "narrative": narrative, "test_suite": suite}
    )


def qa_gate(
    state: V2State, reviewers: dict[QAReviewerKind, QAReviewerLLM]
) -> QAReport:
    """v2 QA 4-charter 리뷰 → QAReport. ``overall_pass`` 가 출하 게이트."""
    reviews: list[QAReview] = [
        reviewers[k].review(state, kind=k).model_copy(update={"kind": k})
        for k in reviewers
    ]
    return QAReport(reviews=tuple(reviews))


def _build_reviewers(
    kinds: tuple[QAReviewerKind, ...] = _EASY_CHARTERS,
) -> dict[QAReviewerKind, QAReviewerLLM]:
    return {k: AnthropicQAReviewerLLM(k) for k in kinds}


def _hybrid_body(
    final: V1State,
    run_id: str,
    seed: str,
    *,
    generator: GradingInputGeneratorLLM,
    runner: CodeRunner,
) -> dict[str, Any]:
    """v1 full success → 풀 채점셋 확장 → persist body.

    ``expand_grading_suite`` (LLM 다양 입력 + verified golden oracle)로 sample 뿐인 v1
    채점셋을 풀셋으로 키운다. 확장 실패(LLM 오류/전부-drop)는 **검증된 문제를 잃지 않도록**
    samples 폴백(가시적 경고) — 적재는 되되 TC 는 sample 수준으로 degrade. golden_origin
    은 reconciliation provenance.
    """
    if final.spec is None or final.attempt is None:  # success 면 항상 set (방어)
        return canonical_body(final, run_id=run_id, seed=seed)
    origin = (
        final.reconciliation.adopted_origin
        if final.reconciliation is not None and final.reconciliation.adopted_origin
        else "golden"
    )
    try:
        suite = expand_grading_suite(
            final.spec,
            final.attempt.code,
            generator=generator,
            runner=runner,
            golden_origin=origin,
        )
    except Exception as exc:  # 확장 실패는 문제 손실 대신 samples 폴백 (per-item 격리)
        print(f"  [{seed:14}] 채점셋 확장 실패({type(exc).__name__}) → samples 폴백")
        return canonical_body(final, run_id=run_id, seed=seed)
    return canonical_body(final, run_id=run_id, seed=seed, test_suite=suite)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m ipe.v2.hybrid_ingest",
        description="하이브리드(v1 생성 + v2 검증) 쉬운 문제 생성 → v2 DB 적재",
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
    reviewers = _build_reviewers()
    input_generator = AnthropicGradingInputGeneratorLLM()
    from ipe.sandbox.selector import pick_runner

    runner = pick_runner()

    persisted = qa_failed = gen_failed = 0
    for seed in seeds:
        for _ in range(args.runs_per_seed):
            run_id = f"hybrid-{seed.value}-{uuid.uuid4().hex[:8]}"
            final = _run_v1_full(seed, run_id, max_iter=args.max_iter)
            if final.final_status != "success":
                gen_failed += 1
                print(f"  [{seed.value:14}] gen {final.final_status} → skip")
                continue
            body = _hybrid_body(
                final,
                run_id,
                seed.value,
                generator=input_generator,
                runner=runner,
            )
            report = qa_gate(_qa_state(body, run_id), reviewers)
            failed_kinds = [r.kind for r in report.reviews if not r.passed]
            body["batch"]["mode"] = "hybrid"
            body["package"]["meta"]["mode"] = "hybrid"
            body["package"]["meta"]["qa"] = {
                "overall_pass": report.overall_pass,
                "failed_kinds": failed_kinds,
            }
            if out_dir is not None:
                (out_dir / f"{seed.value}_{run_id}.json").write_text(
                    json.dumps(body, ensure_ascii=False, indent=2)
                )
            if not report.overall_pass:
                qa_failed += 1
                print(f"  [{seed.value:14}] success but QA FAIL {failed_kinds} → 미적재")
                continue
            n_tc = len(body["package"]["test_suite"]["cases"])
            if engine is not None:
                if difficulty_llm is not None:
                    body = {
                        **body,
                        "package": annotate_difficulty(
                            body["package"], llm=difficulty_llm
                        ),
                    }
                pid = persist_run(engine, body)
                if pid:
                    persisted += 1
                    print(
                        f"  [{seed.value:14}] success + QA pass → DB insert {pid} "
                        f"(채점셋 {n_tc}케이스)"
                    )
            else:
                print(
                    f"  [{seed.value:14}] success + QA pass "
                    f"(DB 미적재, 채점셋 {n_tc}케이스)"
                )
    print(
        f"\n하이브리드: 적재 {persisted} · QA탈락 {qa_failed} · 생성실패 {gen_failed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
