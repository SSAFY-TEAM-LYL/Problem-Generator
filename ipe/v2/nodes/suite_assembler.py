"""suite_assembler 노드 — pending TestSuite + verified golden → assembled (M4 step4).

assembler 엔진(``generation.assembler``)을 감싸는 노드. **LLM 없음**. state.test_suite
(step3 pending) + state.attempt(reconciled canonical, verification 통과한 golden)을 받아
각 입력에 golden 실행 → expected 채운 assembled TestSuite 로 교체. golden_origin 은
reconciliation.adopted_origin(provenance).

runner None 이면 production sandbox(pick_runner) — executor 와 동일.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..generation.assembler import assemble_suite
from ..state import V2State

if TYPE_CHECKING:
    from ipe.v1.verification._exec import CodeRunner


def make_suite_assembler_node(
    *,
    runner: CodeRunner | None = None,
) -> Callable[[V2State], V2State]:
    """factory — pending TestSuite + verified golden(attempt) → assembled TestSuite.

    test 는 mock runner 주입. None 이면 production sandbox.
    """
    resolved_runner: CodeRunner = runner if runner is not None else _default_runner()

    def node(state: V2State) -> V2State:
        suite = state.test_suite
        attempt = state.attempt
        if suite is None or attempt is None:
            msg = "suite_assembler requires state.test_suite and state.attempt"
            raise ValueError(msg)
        origin = "golden"
        if state.reconciliation is not None and state.reconciliation.adopted_origin:
            origin = state.reconciliation.adopted_origin
        assembled = assemble_suite(
            suite, attempt.code, runner=resolved_runner, golden_origin=origin
        )
        return state.model_copy(update={"test_suite": assembled})

    return node


def _default_runner() -> CodeRunner:
    from ipe.sandbox.selector import pick_runner

    return pick_runner()
