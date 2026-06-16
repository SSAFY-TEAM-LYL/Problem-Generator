"""qa_fix(remediation) 단위테스트 — sqlite + mock LLM (실 LLM 불요).

재구성·수정 루프·대상 필터·review 전환을 결정론으로 검증.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, insert, select
from sqlalchemy.engine import Engine

from ipe.v1.schema import ProblemSpec, QAReview, QAReviewerKind
from ipe.v2.db import init_schema, problems, test_cases
from ipe.v2.nodes.qa_reviewer import QAReviewerLLM
from ipe.v2.qa_fix import (
    _finding_texts,
    _spec_from_row,
    _state_from_row,
    apply_remediation,
    load_targets,
    remediate_state,
    run,
)
from ipe.v2.state import V2State

_FAIL = "11111111-1111-1111-1111-111111111111"
_PASS = "22222222-2222-2222-2222-222222222222"


def _engine(tmp_path: Path) -> Engine:
    eng = create_engine(f"sqlite:///{tmp_path / 'bank.db'}")
    init_schema(eng)
    return eng


def _seed(engine: Engine) -> None:
    qa_fail: dict[str, Any] = {
        "overall_pass": False,
        "findings": [
            {"kind": "ambiguity", "severity": "blocker", "description": "N=0 불명확"}
        ],
    }
    qa_pass: dict[str, Any] = {"overall_pass": True, "findings": []}
    common: dict[str, Any] = {
        "input_format": "N",
        "output_format": "int",
        "constraints": [{"name": "N", "min_value": 1, "max_value": 100}],
        "samples": [  # ProblemSpec.sample_testcases ≥3 검증
            {"input_text": "3", "expected_output": "6"},
            {"input_text": "1", "expected_output": "1"},
            {"input_text": "5", "expected_output": "15"},
        ],
        "solution_code": "print(6)",
        "solution_language": "python",
        "status": "draft",
        "time_limit_ms": 2000,
        "algorithm": "dijkstra",
        "created_at": datetime.now(UTC),
    }
    with engine.begin() as c:
        c.execute(
            insert(problems).values(
                id=_FAIL,
                title="fail문제",
                description="모호한 지문",
                internal_meta={
                    "hidden_algorithm": "dijkstra",
                    "domain": "banking",
                    "qa": qa_fail,
                },
                **common,
            )
        )
        c.execute(
            insert(problems).values(
                id=_PASS,
                title="pass문제",
                description="명확한 지문",
                internal_meta={
                    "hidden_algorithm": "bfs",
                    "domain": "logistics",
                    "qa": qa_pass,
                },
                **{**common, "algorithm": "bfs"},
            )
        )
        c.execute(
            insert(test_cases),
            [
                {"problem_id": _FAIL, "seq": 0, "input": "3", "expected": "6",
                 "category": "sample"},
                {"problem_id": _FAIL, "seq": 1, "input": "1", "expected": "1",
                 "category": "edge"},
            ],
        )


class _FixedReviser:
    """scripted 지문 반환 — 호출마다 다음 description."""

    def __init__(self, descriptions: list[str]) -> None:
        self._d = descriptions
        self.calls: list[list[str]] = []

    def revise(self, spec: ProblemSpec, findings: list[str]) -> str:
        self.calls.append(findings)
        return self._d[min(len(self.calls) - 1, len(self._d) - 1)]


class _MarkerReviewer:
    """description 에 marker 가 있으면 pass 하는 mock 리뷰어."""

    def __init__(self, kind: QAReviewerKind, marker: str) -> None:
        self._kind = kind
        self._marker = marker

    def review(self, state: V2State, *, kind: QAReviewerKind) -> QAReview:
        assert state.spec is not None
        passed = self._marker in state.spec.description
        return QAReview(kind=kind, passed=passed)


def _reviewers(marker: str) -> dict[QAReviewerKind, QAReviewerLLM]:
    kinds: tuple[QAReviewerKind, ...] = (
        "ambiguity",
        "fairness",
        "leakage",
        "difficulty",
    )
    out: dict[QAReviewerKind, QAReviewerLLM] = {
        k: _MarkerReviewer(k, marker) for k in kinds
    }
    return out


# ---------- 재구성 ----------
def test_spec_from_row_reconstructs(tmp_path: Path) -> None:
    eng = _engine(tmp_path)
    _seed(eng)
    with eng.connect() as c:
        row = dict(
            c.execute(select(problems).where(problems.c.id == _FAIL)).mappings().one()
        )
    spec = _spec_from_row(row)
    assert spec.title == "fail문제"
    assert spec.target_algorithm.value == "dijkstra"
    assert spec.io_contract.input_format == "N"
    assert len(spec.sample_testcases) == 3


def test_state_from_row_populates_qa_reviewer_inputs(tmp_path: Path) -> None:
    eng = _engine(tmp_path)
    _seed(eng)
    with eng.connect() as c:
        row = dict(
            c.execute(select(problems).where(problems.c.id == _FAIL)).mappings().one()
        )
        cases = [
            dict(x)
            for x in c.execute(
                select(test_cases).where(test_cases.c.problem_id == _FAIL)
            )
            .mappings()
            .all()
        ]
    state = _state_from_row(row, cases, run_id="r1")
    assert state.spec is not None
    assert state.narrative is not None
    assert state.test_suite is not None
    assert len(state.test_suite.cases) == 2
    assert state.narrative.domain == "banking"


def test_finding_texts_handles_dicts() -> None:
    assert _finding_texts([{"description": "a"}, {"description": "b"}]) == ["a", "b"]


# ---------- 대상 필터 ----------
def test_load_targets_only_fail_qa(tmp_path: Path) -> None:
    eng = _engine(tmp_path)
    _seed(eng)
    targets = load_targets(eng)
    assert len(targets) == 1
    assert targets[0]["row"]["id"] == _FAIL
    assert len(targets[0]["cases"]) == 2


# ---------- remediate 루프 ----------
def test_remediate_passes_first_round(tmp_path: Path) -> None:
    eng = _engine(tmp_path)
    _seed(eng)
    with eng.connect() as c:
        row = dict(
            c.execute(select(problems).where(problems.c.id == _FAIL)).mappings().one()
        )
    state = _state_from_row(
        row, [{"input": "3", "expected": "6", "category": "sample"}], run_id="r1"
    )
    reviser = _FixedReviser(["GOOD 명료화된 지문"])
    res = remediate_state(
        state, ["N=0 불명확"], reviser=reviser, reviewers=_reviewers("GOOD"), max_rounds=2
    )
    assert res.passed and res.rounds == 1
    assert reviser.calls[0] == ["N=0 불명확"]  # 1차에 초기 findings 전달


def test_remediate_passes_second_round(tmp_path: Path) -> None:
    eng = _engine(tmp_path)
    _seed(eng)
    with eng.connect() as c:
        row = dict(
            c.execute(select(problems).where(problems.c.id == _FAIL)).mappings().one()
        )
    state = _state_from_row(
        row, [{"input": "3", "expected": "6", "category": "sample"}], run_id="r1"
    )
    reviser = _FixedReviser(["still bad", "GOOD now"])
    res = remediate_state(
        state, ["bad"], reviser=reviser, reviewers=_reviewers("GOOD"), max_rounds=2
    )
    assert res.passed and res.rounds == 2
    assert res.revised_description == "GOOD now"


def test_remediate_best_effort_after_max(tmp_path: Path) -> None:
    eng = _engine(tmp_path)
    _seed(eng)
    with eng.connect() as c:
        row = dict(
            c.execute(select(problems).where(problems.c.id == _FAIL)).mappings().one()
        )
    state = _state_from_row(
        row, [{"input": "3", "expected": "6", "category": "sample"}], run_id="r1"
    )
    reviser = _FixedReviser(["nope1", "nope2"])
    res = remediate_state(
        state, ["bad"], reviser=reviser, reviewers=_reviewers("GOOD"), max_rounds=2
    )
    assert not res.passed and res.rounds == 2


# ---------- apply ----------
def test_apply_remediation_sets_review(tmp_path: Path) -> None:
    eng = _engine(tmp_path)
    _seed(eng)
    apply_remediation(eng, _FAIL, "새 지문")
    with eng.connect() as c:
        row = c.execute(select(problems).where(problems.c.id == _FAIL)).mappings().one()
    assert row["status"] == "review"
    assert row["description"] == "새 지문"


def test_run_end_to_end_applies_passed(tmp_path: Path) -> None:
    eng = _engine(tmp_path)
    _seed(eng)
    results = run(
        eng,
        reviser=_FixedReviser(["GOOD 통과 지문"]),
        reviewers=_reviewers("GOOD"),
        max_rounds=2,
    )
    assert len(results) == 1
    assert results[0]["passed"] and results[0]["applied"]
    with eng.connect() as c:
        row = c.execute(select(problems).where(problems.c.id == _FAIL)).mappings().one()
        passrow = c.execute(
            select(problems).where(problems.c.id == _PASS)
        ).mappings().one()
    assert row["status"] == "review"  # fail_qa → 수정 통과 → review
    assert passrow["status"] == "draft"  # 이미 통과한 건 손 안 댐


def test_run_dry_run_does_not_write(tmp_path: Path) -> None:
    eng = _engine(tmp_path)
    _seed(eng)
    results = run(
        eng,
        reviser=_FixedReviser(["GOOD 지문"]),
        reviewers=_reviewers("GOOD"),
        apply=False,
    )
    assert results[0]["passed"] and not results[0]["applied"]
    with eng.connect() as c:
        row = c.execute(select(problems).where(problems.c.id == _FAIL)).mappings().one()
    assert row["status"] == "draft"  # dry-run 은 쓰기 안 함
