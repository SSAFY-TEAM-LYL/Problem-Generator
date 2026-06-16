"""fail_qa 문제 수정(remediation) 파이프라인 — 재생성 아님(지문 명료화).

이미 적재된 ``status='draft'`` + ``internal_meta.qa.overall_pass=false`` (= QA 미통과) 문제를
집어, QA findings 로 **지문(description)만** 명료화 수정 → QA 재리뷰(4 charter, Sonnet) →
통과 시 ``draft``→``review`` 전환. io_contract·정해·test_cases 는 불변 — 채점 무결성 보존.

기존 in-run back-route(narrative_revise→spec_patch→재리뷰)는 풀 V2State(blueprint.io_schema)
재구성이 취약해 그대로 못 쓴다. 대신 QA 리뷰어가 읽는 최소 상태(spec/narrative/test_suite)만
패키지에서 재구성하고(blueprint optional=None), 신규 reviser 가 지문만 고친다.

기동::

    python -m ipe.v2.qa_fix --db-url "postgresql+psycopg://USER:PW@127.0.0.1:16380/fly-db" \
        --limit 5 --max-rounds 2
"""

from __future__ import annotations

import argparse
import os
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.engine import Engine

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
from ipe.v2.nodes.qa_reviewer import AnthropicQAReviewerLLM, QAReviewerLLM
from ipe.v2.state import V2State, initial_v2_state

from .db.schema import problems, test_cases

QA_FIX_REVISER_MODEL = "claude-sonnet-4-6"
QA_FIX_REVISER_TEMPERATURE = 0.3
_KINDS: tuple[QAReviewerKind, ...] = ("ambiguity", "fairness", "leakage", "difficulty")
_DEFAULT_MAX_ROUNDS = 2


# ---------- 패키지/행 → 최소 V2State 재구성 (QA 재리뷰용) ----------
def _spec_from_row(row: dict[str, Any]) -> ProblemSpec:
    algo = str(
        row.get("algorithm")
        or (row.get("internal_meta") or {}).get("hidden_algorithm")
    )
    constraints = [
        ConstraintRange(**c)
        for c in (row.get("constraints") or [])
        if isinstance(c, dict)
    ]
    samples = [
        SampleTestCase(
            input_text=s.get("input_text", ""),
            expected_output=s.get("expected_output", ""),
        )
        for s in (row.get("samples") or [])
        if isinstance(s, dict)
    ]
    return ProblemSpec(
        target_algorithm=TargetAlgorithm(algo),  # algo: str (위에서 coerce)
        title=row.get("title", ""),
        description=row.get("description", ""),
        io_contract=IOContract(
            input_format=row.get("input_format", ""),
            output_format=row.get("output_format", ""),
        ),
        constraints=constraints,
        sample_testcases=samples,
    )


def _suite_from_cases(cases: list[dict[str, Any]]) -> TestSuite:
    return TestSuite(
        cases=tuple(
            GeneratedTestCase(
                input_text=c.get("input", ""),
                expected_output=c.get("expected", ""),
                category=str(c.get("category") or ""),
            )
            for c in cases
        )
    )


def _state_from_row(
    row: dict[str, Any], cases: list[dict[str, Any]], *, run_id: str
) -> V2State:
    spec = _spec_from_row(row)
    domain = str((row.get("internal_meta") or {}).get("domain") or "")
    narrative = Narrative(scenario=spec.description, hidden=True, domain=domain)
    base = initial_v2_state(run_id, spec.target_algorithm)
    return base.model_copy(
        update={
            "spec": spec,
            "narrative": narrative,
            "test_suite": _suite_from_cases(cases),
        }
    )


def _finding_texts(findings: list[Any]) -> list[str]:
    """findings(dict 또는 Finding 객체) → 설명 문자열 리스트."""
    out: list[str] = []
    for f in findings:
        desc = (
            f.get("description")
            if isinstance(f, dict)
            else getattr(f, "description", None)
        )
        if desc:
            out.append(str(desc))
    return out


# ---------- reviser (신규 LLM) — 지문만 명료화 ----------
class _RevisedDescription(BaseModel):
    description: str = Field(..., min_length=1)


_REVISER_SYSTEM = """\
당신은 출제 검수자다. QA 에서 탈락한 알고리즘 문제의 **지문(description)만** 수정한다.

엄격 규칙:
- 입력/출력 형식의 **의미**, 샘플 입출력, 제약, 숨은 알고리즘은 **절대 바꾸지 않는다**.
  (정해 코드·채점 test_cases 가 그대로 유효해야 한다.)
- QA findings(모호성/공정성/유출/난이도 지적)를 해소하도록 **문구·경계·정의를 명료화**만 한다.
- 유효 입력 집합이나 기대 출력이 달라지는 변경 금지. 오직 같은 문제를 더 명확히 기술.
- 반환: 수정된 description 전문 (구조화된 tool call).
"""


class QAFixReviserLLM(Protocol):
    """reviser dependency — test 가 mock 주입."""

    def revise(self, spec: ProblemSpec, findings: list[str]) -> str: ...


class AnthropicQAFixReviser:
    """production impl — Sonnet, 지문만 수정."""

    def __init__(self, model: str = QA_FIX_REVISER_MODEL) -> None:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatAnthropic(
            model_name=model,
            temperature=QA_FIX_REVISER_TEMPERATURE,
            timeout=60,
            stop=None,
        )
        prompt = ChatPromptTemplate.from_messages(
            [("system", _REVISER_SYSTEM), ("user", "{user}")]
        )
        self._chain = (
            prompt | llm.with_structured_output(_RevisedDescription)
        ).with_retry(stop_after_attempt=5, wait_exponential_jitter=True)

    def revise(self, spec: ProblemSpec, findings: list[str]) -> str:
        user = "\n".join(
            [
                f"title: {spec.title}",
                f"input_format: {spec.io_contract.input_format}",
                f"output_format: {spec.io_contract.output_format}",
                "samples:",
                *(
                    f"  in={s.input_text!r} out={s.expected_output!r}"
                    for s in spec.sample_testcases[:2]
                ),
                "",
                "[현재 지문]",
                spec.description,
                "",
                "[QA 지적사항 — 이걸 해소하도록 지문만 명료화]",
                *(f"  - {t}" for t in findings),
            ]
        )
        result = self._chain.invoke({"user": user})
        if not isinstance(result, _RevisedDescription):
            msg = f"reviser 가 {type(result).__name__} 반환 — _RevisedDescription 기대"
            raise TypeError(msg)
        return result.description


# ---------- 재리뷰 (기존 리뷰어 재사용) ----------
def _build_reviewers() -> dict[QAReviewerKind, QAReviewerLLM]:
    return {kind: AnthropicQAReviewerLLM(kind) for kind in _KINDS}


def _re_review(
    state: V2State, reviewers: dict[QAReviewerKind, QAReviewerLLM]
) -> QAReport:
    reviews: list[QAReview] = []
    for kind in _KINDS:
        review = reviewers[kind].review(state, kind=kind)
        reviews.append(review.model_copy(update={"kind": kind}))
    return QAReport(reviews=tuple(reviews))


# ---------- remediation 루프 ----------
@dataclass(frozen=True)
class RemediationResult:
    passed: bool
    rounds: int
    revised_description: str
    report: QAReport


def remediate_state(
    state: V2State,
    initial_findings: list[str],
    *,
    reviser: QAFixReviserLLM,
    reviewers: dict[QAReviewerKind, QAReviewerLLM],
    max_rounds: int = _DEFAULT_MAX_ROUNDS,
) -> RemediationResult:
    """지문 수정 → 재리뷰 루프. 통과한 지문/리포트 반환, 소진 시 마지막 best-effort."""
    if state.spec is None:
        msg = "remediate_state requires state.spec"
        raise ValueError(msg)
    findings = initial_findings
    last_desc = state.spec.description
    last_report: QAReport | None = None
    for i in range(max_rounds):
        last_desc = reviser.revise(state.spec, findings)
        spec = state.spec.model_copy(update={"description": last_desc})
        narrative = (
            state.narrative.model_copy(update={"scenario": last_desc})
            if state.narrative is not None
            else None
        )
        state = state.model_copy(update={"spec": spec, "narrative": narrative})
        last_report = _re_review(state, reviewers)
        if last_report.overall_pass:
            return RemediationResult(True, i + 1, last_desc, last_report)
        findings = _finding_texts(
            [f for r in last_report.reviews for f in r.findings]
        )
    assert last_report is not None
    return RemediationResult(False, max_rounds, last_desc, last_report)


# ---------- DB 적재/조회 ----------
def load_targets(engine: Engine, *, limit: int | None = None) -> list[dict[str, Any]]:
    """remediation 대상 — draft + internal_meta.qa.overall_pass=false 인 문제 + 케이스."""
    targets: list[dict[str, Any]] = []
    with engine.connect() as conn:
        rows = (
            conn.execute(select(problems).where(problems.c.status == "draft"))
            .mappings()
            .all()
        )
        for row in rows:
            qa = (row["internal_meta"] or {}).get("qa") or {}
            if qa.get("overall_pass") is not False:
                continue  # QA 통과했거나 QA 정보 없음 — 대상 아님
            cases = (
                conn.execute(
                    select(test_cases)
                    .where(test_cases.c.problem_id == row["id"])
                    .order_by(test_cases.c.seq)
                )
                .mappings()
                .all()
            )
            targets.append({"row": dict(row), "cases": [dict(c) for c in cases]})
            if limit is not None and len(targets) >= limit:
                break
    return targets


def apply_remediation(engine: Engine, problem_id: str, new_description: str) -> None:
    """수정된 지문 반영 + draft→review 전환 (사람 검수 단계)."""
    with engine.begin() as conn:
        conn.execute(
            update(problems)
            .where(problems.c.id == problem_id)
            .values(description=new_description, status="review")
        )


def run(
    engine: Engine,
    *,
    reviser: QAFixReviserLLM | None = None,
    reviewers: dict[QAReviewerKind, QAReviewerLLM] | None = None,
    limit: int | None = None,
    max_rounds: int = _DEFAULT_MAX_ROUNDS,
    apply: bool = True,
) -> list[dict[str, Any]]:
    """fail_qa 대상 일괄 remediation. 통과분만 ``apply`` 시 review 전환."""
    reviser = reviser or AnthropicQAFixReviser()
    reviewers = reviewers or _build_reviewers()
    results: list[dict[str, Any]] = []
    for target in load_targets(engine, limit=limit):
        row = target["row"]
        run_id = uuid.uuid4().hex
        state = _state_from_row(row, target["cases"], run_id=run_id)
        findings = _finding_texts(
            ((row.get("internal_meta") or {}).get("qa") or {}).get("findings") or []
        )
        res = remediate_state(
            state,
            findings,
            reviser=reviser,
            reviewers=reviewers,
            max_rounds=max_rounds,
        )
        if res.passed and apply:
            apply_remediation(engine, row["id"], res.revised_description)
        results.append(
            {
                "problem_id": row["id"],
                "algorithm": row.get("algorithm"),
                "passed": res.passed,
                "rounds": res.rounds,
                "applied": res.passed and apply,
            }
        )
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="fail_qa 문제 지문 수정 remediation")
    parser.add_argument("--db-url", default=os.environ.get("IPE_ADMIN_DB_URL"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-rounds", type=int, default=_DEFAULT_MAX_ROUNDS)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="수정·재리뷰만, review 전환(쓰기) 안 함",
    )
    args = parser.parse_args(argv)
    if not args.db_url:
        raise SystemExit("--db-url 또는 env IPE_ADMIN_DB_URL 필요")

    from sqlalchemy import create_engine

    engine = create_engine(args.db_url, pool_pre_ping=True)
    results = run(
        engine, limit=args.limit, max_rounds=args.max_rounds, apply=not args.dry_run
    )
    n_pass = sum(1 for r in results if r["passed"])
    n_applied = sum(1 for r in results if r["applied"])
    print(f"[qa_fix] 대상 {len(results)} · 통과 {n_pass} · 적용 {n_applied}")
    for r in results:
        mark = "✓review" if r["applied"] else ("pass(dry)" if r["passed"] else "fail")
        print(f"  [{r['algorithm']:14}] {mark:10} rounds={r['rounds']} {r['problem_id']}")


if __name__ == "__main__":
    main()
