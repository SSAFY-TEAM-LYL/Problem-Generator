"""Strategist 노드 — seed_algorithm hint → StrategySeed (M3 step2, blueprint-first).

LLM: Sonnet 4.6 (발산적 시드). 책임 = **무엇을 숨길지**(reduction_core) + 합성 기법
+ **위장 도메인**(domain) 결정. 형식 동결(io_schema/invariants)은 Formalizer(Opus)로
분리 — Q1 = 분리 확정.

``with_structured_output(StrategySeed)`` 로 typed deserialize (prose parsing 없음).
factory/Protocol/lazy-Anthropic 패턴은 v1 architect 와 동일.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ipe.v1.schema import StrategySeed, TargetAlgorithm

from ..state import V2State

STRATEGIST_MODEL = "claude-sonnet-4-6"
STRATEGIST_TEMPERATURE = 0.7  # 발산적 위장 다양성 (Formalizer 의 0.2 와 대비)

# enum 허용값을 prompt 에 명시 — 모델이 'greedy' 같은 목록 밖 자연어 기법을 emit 해
# structured output 검증이 retry 전부 실패하는 것을 방지 (M4 step5 e2e 실측 발견).
_VALID_ALGORITHMS = ", ".join(a.value for a in TargetAlgorithm)

_SYSTEM_PROMPT = f"""\
당신은 algorithmic problem strategist 다. 주어진 target algorithm hint 를 받아,
그 알고리즘을 **은닉**한 코딩테스트 문제의 전략 시드를 설계한다.

typed StrategySeed (구조화된 tool call) 로 반환:
- reduction_core: 숨길 핵심 알고리즘 (보통 hint 와 동일하거나 그 환원). solver 가
  지문만 보고 바로 알아채지 못하게 할 대상.
- composition: reduction_core 외 합성할 추가 기법들 (없으면 빈 list). 난이도·위장
  강화를 위해 1~2개 결합 가능.
- domain: 현실 세계 도메인 (예: 'logistics', 'social-network', 'genomics'). 이
  도메인의 시나리오로 알고리즘이 자연스럽게 위장되어야 한다.
- rationale: 이 위장이 왜 reduction_core 를 효과적으로 숨기는지 한 줄 근거.

reduction_core 와 composition 의 모든 원소는 **반드시 다음 값 중에서만** 골라야 한다:
{_VALID_ALGORITHMS}.
이 목록 밖 기법(예: 'greedy', 'two_pointers', 'sliding_window')은 schema 검증에서
거부된다 — 그런 기법을 섞고 싶으면 목록 내 가장 가까운 값을 쓰거나 composition 을
비워 둔다.

composition 다양성 (유출 게이트 실측 반영):
- reduction_core 의 표준 구현에 **이미 내장된** 기법은 composition 에 넣지 말 것
  (예: dijkstra 의 heap/우선순위 큐) — 합성 강제력이 없는 장식이라 문제를 바꾸지
  못한다.
- 가장 흔한 합성 패턴 하나에 **고정되지 말 것**: 특히 '임계값 feasibility 이분
  탐색(binary_search)' 패턴은 **과사용**되어 유출 게이트가 고전 동형(예: bottleneck
  shortest path)으로 reject 하기 쉽다. 출력 의미를 바꾸는 다른 합성 축도 적극
  고려하라 — 집계/계수(knapsack/coin_change/lis), 전처리·정렬(sort), 누적 질의
  (fenwick/segtree), 연결성 전처리(union_find) 등 reduction_core 와 자연스럽게
  결합되는 것 중에서 고른다.

핵심 목표 (은닉): domain 시나리오만 읽고는 reduction_core 가 무엇인지 **바로 드러나지
않아야** 한다. 그러나 형식적으로는 정확히 그 알고리즘으로 환원되어야 한다. 형식 동결
(입출력 스키마/불변식)은 다음 단계(Formalizer)가 담당하므로 여기서는 전략만 정한다.
"""


def _build_user_prompt(state: V2State) -> str:
    return "\n".join(
        [
            f"target algorithm hint: {state.seed_algorithm.value}",
            f"run_id: {state.run_id}",
        ]
    )


class StrategistLLM(Protocol):
    """Strategist 의 LLM dependency. test 가 mock 주입."""

    def seed(self, state: V2State) -> StrategySeed: ...


class AnthropicStrategistLLM:
    """production impl — Sonnet + structured output. lazy import (test 는 mock)."""

    def __init__(self, model: str = STRATEGIST_MODEL) -> None:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatAnthropic(model_name=model, timeout=60, stop=None)
        prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM_PROMPT), ("user", "{user}")]
        )
        self._chain = (prompt | llm.with_structured_output(StrategySeed)).with_retry(
            stop_after_attempt=5, wait_exponential_jitter=True
        )

    def seed(self, state: V2State) -> StrategySeed:
        result = self._chain.invoke({"user": _build_user_prompt(state)})
        if not isinstance(result, StrategySeed):
            msg = (
                f"with_structured_output 가 {type(result).__name__} 반환 — "
                "StrategySeed 기대"
            )
            raise TypeError(msg)
        return result


def make_strategist_node(
    llm: StrategistLLM | None = None,
) -> Callable[[V2State], V2State]:
    """factory — graph build 시 호출. test 는 mock LLM 주입."""
    resolved_llm: StrategistLLM = (
        llm if llm is not None else AnthropicStrategistLLM()
    )

    def node(state: V2State) -> V2State:
        seed = resolved_llm.seed(state)
        return state.model_copy(update={"strategy": seed})

    return node
