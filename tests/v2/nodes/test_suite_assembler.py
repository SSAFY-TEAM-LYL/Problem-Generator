"""suite_assembler 노드 단위 테스트 (Phase 3 M4 step4).

- ``make_suite_assembler_node`` (LLM 없음): pending test_suite + verified golden(attempt)
  → assembled(expected 채움). golden_origin=reconciliation.adopted_origin.
"""

from __future__ import annotations

import pytest

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import (
    GeneratedTestCase,
    ReconciliationResult,
    SolutionAttempt,
    TargetAlgorithm,
    TestSuite,
)
from ipe.v2.nodes import make_suite_assembler_node
from ipe.v2.state import V2State, initial_v2_state


class _EchoRunner:
    def run(self, spec: RunSpec) -> RunResult:
        return RunResult(
            status="OK",
            returncode=0,
            stdout=f"out:{spec.stdin}\n",
            stderr="",
            elapsed_ms=1,
        )


def _pending() -> TestSuite:
    return TestSuite(
        cases=(
            GeneratedTestCase(input_text="1", category="small"),
            GeneratedTestCase(input_text="2", category="small"),
        )
    )


def _state(
    *, with_suite: bool = True, with_attempt: bool = True, origin: str = "opus"
) -> V2State:
    base = initial_v2_state("run-v2", TargetAlgorithm.SORT)
    update: dict[str, object] = {}
    if with_suite:
        update["test_suite"] = _pending()
    if with_attempt:
        update["attempt"] = SolutionAttempt(code="# golden", iteration=0)
        update["reconciliation"] = ReconciliationResult(
            candidate_count=3,
            all_agree=True,
            canonical_code="# golden",
            adopted_origin=origin,
        )
    return base.model_copy(update=update)


def test_assembler_node_fills_and_sets_origin() -> None:
    out = make_suite_assembler_node(runner=_EchoRunner())(_state())
    suite = out.test_suite
    assert suite is not None
    assert suite.is_assembled is True
    assert suite.golden_origin == "opus"
    assert [c.expected_output for c in suite.cases] == ["out:1", "out:2"]


def test_assembler_records_golden_elapsed_ms() -> None:
    """B2C 계약 v1.0: 케이스별 golden 실행시간을 기록 — 백엔드가 문제별
    TL(시간제한)을 max_golden_elapsed_ms × 배수로 산정하는 근거."""
    out = make_suite_assembler_node(runner=_EchoRunner())(_state())
    suite = out.test_suite
    assert suite is not None
    assert [c.golden_elapsed_ms for c in suite.cases] == [1, 1]


def test_assembler_node_requires_suite_and_attempt() -> None:
    node = make_suite_assembler_node(runner=_EchoRunner())
    with pytest.raises(ValueError, match="test_suite"):
        node(_state(with_suite=False))
    with pytest.raises(ValueError, match="attempt"):
        node(_state(with_attempt=False))


def test_assembler_node_preserves_pending_original() -> None:
    state = _state()
    out = make_suite_assembler_node(runner=_EchoRunner())(state)
    assert state.test_suite is not None and state.test_suite.is_assembled is False
    assert out.test_suite is not None and out.test_suite.is_assembled is True
