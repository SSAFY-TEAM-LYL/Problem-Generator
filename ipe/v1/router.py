"""v1 fix-loop router (D안 PR-A3).

``VerificationResult.feedback.target_node`` enum 으로 결정론적 dispatch +
``blocking_signature`` 누적으로 oscillation detection (사용자 결정 threshold = 2).

v0 의 ``last_failed_node: str`` + prose feedback 의 semantic drift 위험 차단 —
D안 H1 의 "결정론적 routing" 약속 구현.
"""

from __future__ import annotations

from typing import Literal

from .schema import TargetNode
from .state import V1State

OSCILLATION_THRESHOLD = 2

RouterDecision = Literal[
    "architect",
    "designer",
    "coder",
    "end_success",
    "end_budget",
    "end_schema_violation",
    "end_oscillation",
]


def route_after_executor(state: V1State) -> RouterDecision:
    """executor 후 다음 step 결정.

    Decision tree (순서 중요):

    1. ``verification`` 가 None (executor 비정상 종료) → coder retry.
    2. ``overall_pass=True`` → end_success.
    3. ``feedback`` 가 None (pass=False 인데 feedback 없음, schema 위반) →
       end_schema_violation. (H1 측정시 진짜 ``end_budget`` 과 분리하기 위해
       별도 final_status — watchdog WATCH.md 12:00 entry 참조)
    4. ``blocking_signature`` 가 prior iterations 에서 ``OSCILLATION_THRESHOLD``
       회 이상 누적 → end_oscillation.
    5. ``iteration >= max_iterations`` → end_budget.
    6. ``feedback.target_node`` enum dispatch:
       - ``ARCHITECT`` → architect 재실행.
       - ``DESIGNER`` → designer 재실행.
       - ``CODER`` / ``AUDITOR`` / ``GENERATOR`` → coder 재실행 (Phase 1 은
         auditor/generator 미사용 — coder fallback).
    """
    v = state.verification
    if v is None:
        return "coder"
    if v.overall_pass:
        return "end_success"
    if v.feedback is None:
        return "end_schema_violation"

    sig = v.feedback.blocking_signature
    same_sig_count = sum(
        1 for record in state.context.iterations if record.blocking_signature == sig
    )
    if same_sig_count >= OSCILLATION_THRESHOLD:
        return "end_oscillation"

    if state.iteration >= state.max_iterations:
        return "end_budget"

    target = v.feedback.target_node
    if target == TargetNode.ARCHITECT:
        return "architect"
    if target == TargetNode.DESIGNER:
        return "designer"
    # CODER + Phase 1 미사용 (AUDITOR/GENERATOR) → coder fallback
    return "coder"


# ---- full mode (Phase 3 M2 step4) routers ----

ReconcileDecision = Literal["synth_bridge", "end_synthesis_rejected"]
FullExecutorDecision = Literal["end_success", "end_verification_fail"]


def route_after_reconcile(state: V1State) -> ReconcileDecision:
    """full mode fan-in 후: canonical 채택 여부로 분기.

    - ``reconciliation.canonical_code`` 채택됨 → ``synth_bridge`` (attempt 로 bridge).
    - reconcile reject (불일치/crash/golden부재/후보<2) → ``end_synthesis_rejected``.
    """
    r = state.reconciliation
    if r is not None and r.canonical_code is not None:
        return "synth_bridge"
    return "end_synthesis_rejected"


def route_after_full_executor(state: V1State) -> FullExecutorDecision:
    """full mode single-shot: executor 검증 결과로 종료 분기 (fix loop 없음).

    - ``verification.overall_pass`` → ``end_success``.
    - 그 외 (sample mismatch / invariant violation / verification 부재) →
      ``end_verification_fail``. 반복 정제는 M3+ 범위 (step4 는 단발 출하가능률 측정).
    """
    v = state.verification
    if v is not None and v.overall_pass:
        return "end_success"
    return "end_verification_fail"
