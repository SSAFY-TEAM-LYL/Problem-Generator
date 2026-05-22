"""v1 fix-loop router 단위 테스트 (D안 PR-A3)."""

from __future__ import annotations

from ipe.v1.router import OSCILLATION_THRESHOLD, route_after_executor
from ipe.v1.schema import (
    FailureMode,
    IterationContext,
    IterationRecord,
    StructuredFeedback,
    TargetAlgorithm,
    TargetNode,
    VerificationResult,
)
from ipe.v1.state import V1State


def _state(
    *,
    iteration: int = 0,
    max_iterations: int = 8,
    verification: VerificationResult | None = None,
    iterations: list[IterationRecord] | None = None,
) -> V1State:
    ctx = IterationContext(
        run_id="r1",
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        iterations=iterations or [],
    )
    return V1State(
        run_id="r1",
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        iteration=iteration,
        max_iterations=max_iterations,
        verification=verification,
        context=ctx,
    )


def _fail_verification(
    target: TargetNode = TargetNode.CODER,
    *,
    sig: str = "sig-x",
    failure_mode: FailureMode = FailureMode.INVARIANT_VIOLATION,
    iteration: int = 1,
) -> VerificationResult:
    return VerificationResult(
        overall_pass=False,
        failure_mode=failure_mode,
        feedback=StructuredFeedback(
            target_node=target, actionable_hint="x", blocking_signature=sig
        ),
        iteration=iteration,
    )


def test_routes_end_success_when_overall_pass() -> None:
    v = VerificationResult(
        overall_pass=True, failure_mode=FailureMode.NONE, iteration=0
    )
    state = _state(verification=v)
    assert route_after_executor(state) == "end_success"


def test_routes_coder_when_target_node_coder() -> None:
    state = _state(iteration=1, verification=_fail_verification(TargetNode.CODER))
    assert route_after_executor(state) == "coder"


def test_routes_architect_when_target_node_architect() -> None:
    state = _state(
        iteration=1, verification=_fail_verification(TargetNode.ARCHITECT)
    )
    assert route_after_executor(state) == "architect"


def test_routes_designer_when_target_node_designer() -> None:
    state = _state(iteration=1, verification=_fail_verification(TargetNode.DESIGNER))
    assert route_after_executor(state) == "designer"


def test_routes_coder_for_phase2_only_targets() -> None:
    """AUDITOR/GENERATOR 는 Phase 1 미사용 — coder fallback."""
    state_a = _state(iteration=1, verification=_fail_verification(TargetNode.AUDITOR))
    state_g = _state(
        iteration=1, verification=_fail_verification(TargetNode.GENERATOR)
    )
    assert route_after_executor(state_a) == "coder"
    assert route_after_executor(state_g) == "coder"


def test_routes_end_budget_when_iteration_at_max() -> None:
    state = _state(
        iteration=8,
        max_iterations=8,
        verification=_fail_verification(iteration=8),
    )
    assert route_after_executor(state) == "end_budget"


def test_routes_end_oscillation_when_signature_at_threshold() -> None:
    sig = "dijkstra-bug"
    prior_records = [
        IterationRecord(
            iter_index=i,
            node="coder",
            failure_mode=FailureMode.INVARIANT_VIOLATION,
            blocking_signature=sig,
            timestamp_iso="2026-05-22T00:00:00Z",
        )
        for i in range(OSCILLATION_THRESHOLD)
    ]
    state = _state(
        iteration=3,
        verification=_fail_verification(sig=sig, iteration=3),
        iterations=prior_records,
    )
    assert route_after_executor(state) == "end_oscillation"


def test_routes_coder_when_below_oscillation_threshold() -> None:
    sig = "dijkstra-bug"
    prior_records = [
        IterationRecord(
            iter_index=0,
            node="coder",
            failure_mode=FailureMode.INVARIANT_VIOLATION,
            blocking_signature=sig,
            timestamp_iso="2026-05-22T00:00:00Z",
        )
    ]
    state = _state(
        iteration=1,
        verification=_fail_verification(sig=sig, iteration=1),
        iterations=prior_records,
    )
    # threshold = 2, 누적 1 → not yet
    assert route_after_executor(state) == "coder"


def test_routes_end_schema_violation_when_pass_false_but_feedback_none() -> None:
    """schema 위반은 진짜 budget 소진과 별도 final_status (WATCH.md 12:00 entry)."""
    v = VerificationResult(
        overall_pass=False, failure_mode=FailureMode.UNKNOWN, feedback=None, iteration=0
    )
    state = _state(verification=v)
    assert route_after_executor(state) == "end_schema_violation"


def test_routes_coder_when_verification_none() -> None:
    """executor 가 verification 안 채운 비정상 케이스 — coder graceful retry."""
    state = _state(verification=None)
    assert route_after_executor(state) == "coder"


def test_oscillation_threshold_is_two() -> None:
    """사용자 결정: v0 R-osc-break 패턴 = 2."""
    assert OSCILLATION_THRESHOLD == 2
