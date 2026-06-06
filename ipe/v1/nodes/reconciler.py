"""Reconciler fan-in 노드 — candidates 채널을 reconcile() 로 canonical 채택 (M2 step3).

K golden + brute 가 reducer 채널(``state.candidates``)에 누적된 뒤 **1회** 실행되는
fan-in 노드. M2 step2 의 순수 로직 ``reconcile()`` 를 호출해 ``ReconciliationResult``
를 ``state.reconciliation`` 에 기록한다 (partial dict ``{"reconciliation": r}``).

differential 입력 샘플은 ``state.spec.sample_testcases`` 의 ``input_text`` 에서 추출 —
reconcile 은 reference golden 기준 나머지 후보를 이 입력들로 차분한다 (M1 재사용).
LLM 없음 — runner 주입 (단위/통합 테스트는 scripted mock).
"""

from __future__ import annotations

from collections.abc import Callable

from ..schema import ProblemSpec, ReconciliationResult
from ..state import V1State
from ..verification._exec import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIME_LIMIT_MS,
    CodeRunner,
)
from ..verification.reconcile import reconcile


def _sample_inputs(spec: ProblemSpec) -> list[str]:
    return [s.input_text for s in spec.sample_testcases]


def make_reconciler_node(
    runner: CodeRunner,
    *,
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> Callable[[V1State], dict[str, ReconciliationResult]]:
    """fan-in reconciler 노드 — ``state.candidates`` 를 reconcile 해 결과 기록.

    입력 샘플은 ``state.spec`` 에서 추출하므로 spec 이 없으면 차분 불가 → 예외.
    """

    def node(state: V1State) -> dict[str, ReconciliationResult]:
        if state.spec is None:
            msg = "reconciler requires state.spec (differential inputs 추출용)"
            raise ValueError(msg)
        result = reconcile(
            candidates=state.candidates,
            inputs=_sample_inputs(state.spec),
            runner=runner,
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )
        return {"reconciliation": result}

    return node
