"""synth_bridge 노드 — reconciliation canonical → SolutionAttempt (M2 step4 full mode).

full mode 의 fan-in(reconciler) 이 canonical 을 채택하면, 그 ``canonical_code`` 를
기존 executor 가 검증할 수 있는 ``SolutionAttempt`` (``state.attempt``) 로 bridge
한다. 덕분에 canonical/full 두 mode 가 **동일한 executor/verifier 경로**로 합류한다.

route 가드(``route_after_reconcile``)가 canonical 채택 시에만 이 노드로 보내므로
``canonical_code`` 는 not None 이 보장된다 (방어적으로 재확인).

반환은 **partial dict** ``{"attempt": a}`` — reducer 채널(candidates)을 재emit 하지
않아 안전 (step3 발견). LLM 없음.
"""

from __future__ import annotations

from collections.abc import Callable

from ..schema import SolutionAttempt
from ..state import V1State


def make_synth_bridge_node() -> Callable[[V1State], dict[str, SolutionAttempt]]:
    """reconciliation 의 canonical_code 를 SolutionAttempt 로 변환하는 노드 팩토리."""

    def node(state: V1State) -> dict[str, SolutionAttempt]:
        r = state.reconciliation
        if r is None or r.canonical_code is None:
            msg = (
                "synth_bridge requires adopted canonical_code "
                "(route_after_reconcile guard 위반)"
            )
            raise ValueError(msg)
        attempt = SolutionAttempt(code=r.canonical_code, iteration=state.iteration)
        return {"attempt": attempt}

    return node
