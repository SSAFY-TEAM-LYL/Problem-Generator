"""Reconciler (N5) — K golden + brute 상호 일치 확인 + canonical 채택 (Phase 3 M2).

병렬 Solution Synthesis 의 fan-in 코드 노드 로직. reference golden(최소 fanout_index)
을 기준으로 나머지 golden·brute 후보를 **differential**(M1 재사용)로 비교한다.

- 모든 후보가 reference 와 일치 → reference 를 canonical 채택 (all_agree=True).
- 하나라도 불일치(또는 crash/TLE) → reject 신호 (canonical None + disagreements).
- golden 부재 → 채택 불가. 후보 < 2 → 교차검증 불가 → 미채택 (vacuous 금지).

RFC §7.4 brute 독립성: 일치는 '독립 출처가 같은 답에 수렴' 이라야 의미가 있으므로
``origin`` 라벨로 출처를 기록만 하고, 신뢰 판단은 differential 결과로 한다.
LLM 없음 — runner 주입 (단위 테스트는 mock).
"""

from __future__ import annotations

from collections.abc import Sequence

from ..schema import ReconciliationResult, SolutionCandidate
from ._exec import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIME_LIMIT_MS,
    CodeRunner,
)
from .differential import run_differential


def reconcile(
    *,
    candidates: Sequence[SolutionCandidate],
    inputs: Sequence[str],
    runner: CodeRunner,
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> ReconciliationResult:
    """후보들을 reference golden 기준 differential 로 reconcile."""
    count = len(candidates)
    goldens = sorted(
        (c for c in candidates if c.role == "golden"),
        key=lambda c: (c.fanout_index, c.origin),
    )
    if not goldens:
        return ReconciliationResult(
            candidate_count=count,
            all_agree=False,
            canonical_code=None,
            adopted_origin=None,
            disagreements=("no golden candidate to adopt as canonical",),
        )
    reference = goldens[0]
    others = [c for c in candidates if c is not reference]
    if not others:
        return ReconciliationResult(
            candidate_count=count,
            all_agree=False,
            canonical_code=None,
            adopted_origin=None,
            disagreements=("insufficient candidates for cross-check (need >= 2)",),
        )

    disagreements: list[str] = []
    for cand in sorted(others, key=lambda c: (c.role, c.fanout_index, c.origin)):
        report = run_differential(
            golden_code=reference.code,
            brute_code=cand.code,
            inputs=inputs,
            runner=runner,
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )
        if not report.all_agreed:
            disagreements.append(
                f"{reference.origin} vs {cand.origin} ({cand.role}): "
                f"differ on {len(report.disagreements)}/{report.total} input(s)"
            )

    all_agree = len(disagreements) == 0
    return ReconciliationResult(
        candidate_count=count,
        all_agree=all_agree,
        canonical_code=reference.code if all_agree else None,
        adopted_origin=reference.origin if all_agree else None,
        disagreements=tuple(disagreements),
    )
