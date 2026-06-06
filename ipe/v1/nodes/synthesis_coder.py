"""병렬 solution synth coder 노드 — CoderLLM 을 SolutionCandidate emit 으로 wrap (M2 step3).

기존 ``make_coder_node`` 는 단일경로(SolutionAttempt → ``state.attempt``). 병렬 영역은
같은 ``CoderLLM.generate(state) -> SolutionAttempt`` 를 **재사용**하되, 결과를
``role``/``origin`` 라벨된 ``SolutionCandidate`` 로 감싸 reducer 채널(``candidates``)에
append 한다.

fan-out 단위: golden×K (origin 다른 LLM) + brute×1. 각 노드는 **partial dict**
``{"candidates": [c]}`` 반환 (M0 스파이크 Q3 — 전체 state 반환은 reducer 중복 위험).
라벨(role/origin/fanout_index)은 노드가 부여하고 LLM 은 코드만 생성 — origin 으로
differential 독립성 전제(§7.4)를 추적한다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from ..schema import SolutionCandidate
from ..state import V1State
from .coder import CoderLLM


def make_synthesis_coder_node(
    llm: CoderLLM,
    *,
    role: Literal["golden", "brute"],
    origin: str,
    fanout_index: int = 0,
) -> Callable[[V1State], dict[str, list[SolutionCandidate]]]:
    """``CoderLLM`` 을 ``SolutionCandidate`` emit 노드로 변환 (fan-out 병렬 단위).

    ``role``/``origin``/``fanout_index`` 라벨은 노드가 부여 (LLM 은 코드만 생성).
    반환은 partial dict — reducer(``operator.add``)가 ``candidates`` 채널에 누적.
    """

    def node(state: V1State) -> dict[str, list[SolutionCandidate]]:
        if state.spec is None or state.design is None:
            msg = "synthesis coder requires state.spec and state.design"
            raise ValueError(msg)
        attempt = llm.generate(state)
        candidate = SolutionCandidate(
            role=role,
            origin=origin,
            code=attempt.code,
            language=attempt.language,
            fanout_index=fanout_index,
        )
        return {"candidates": [candidate]}

    return node
