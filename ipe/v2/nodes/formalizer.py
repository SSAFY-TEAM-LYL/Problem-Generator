"""Formalizer 노드 — StrategySeed → ProblemBlueprint FREEZE (M3 step2, blueprint-first).

LLM: Opus 4.7 (정밀 형식 동결). 책임 = frozen strategy 위에 io_schema +
output_invariants 를 붙여 ``ProblemBlueprint`` 로 **freeze**. 알고리즘 결정
(reduction_core/composition/domain)은 Strategist 가 정한 것을 노드가 **구조적으로
carry-over** — Formalizer LLM 은 ``BlueprintFormalization``(형식 면만) 만 산출하므로
은닉 코어를 임의로 바꿀 수 없다 (freeze 규율, 상관오독 §7 방어).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ipe.v1.schema import BlueprintFormalization, ProblemBlueprint

from ..state import V2State

FORMALIZER_MODEL = "claude-opus-4-7"
FORMALIZER_TEMPERATURE = 0.2  # 정밀 동결 (발산 금지, Strategist 의 0.7 와 대비)


_SYSTEM_PROMPT = """\
당신은 algorithmic problem formalizer 다. 이미 정해진 전략 시드(숨은 알고리즘 +
합성 기법 + 위장 도메인)를 받아, 그 문제의 **형식 계약**을 정밀하게 동결한다.

typed BlueprintFormalization (구조화된 tool call) 로 반환 — 형식 면만:
- io_schema:
  - inputs: 입력 각 필드의 IOFieldSpec (name + type + size_range/value_range).
    type 은 int / int_array / int_matrix / float / string / bool / weighted_edges /
    tree_edges / grid 중. 크기·값 범위를 ConstraintRange 로 명시.
  - output_type: int / int_array / float / bool / string / yes_no 중.
  - output_format: 출력 인쇄 형식 (한 줄 설명).
- output_invariants: 출력이 **항상** 만족하는 관계 (symbolic invariant 후보). 각
  kind + description. 예: non_negative / monotonic / sum_conserved / bounded_by_input.

규율:
- 알고리즘/도메인을 **재결정하지 말 것** — 시드의 reduction_core/composition/domain
  은 이미 동결되어 그대로 유지된다. 당신은 입출력 형식과 불변식만 형식화한다.
- io_schema 는 정답을 노출하지 않는 **중립 형식 계약** 이어야 한다 (은닉 유지).
- output_invariants 는 정답 검증에 쓰일 만큼 구체적이되 풀이를 누설하지 않게.
"""


def _build_user_prompt(state: V2State) -> str:
    strategy = state.strategy
    if strategy is None:
        msg = "formalizer requires state.strategy — strategist must run first"
        raise ValueError(msg)
    parts = [
        f"reduction_core (숨은 알고리즘): {strategy.reduction_core.value}",
        f"composition (합성 기법): {[a.value for a in strategy.composition]}",
        f"domain (위장 도메인): {strategy.domain}",
    ]
    if strategy.rationale:
        parts.append(f"rationale: {strategy.rationale}")
    return "\n".join(parts)


class FormalizerLLM(Protocol):
    """Formalizer 의 LLM dependency. test 가 mock 주입."""

    def formalize(self, state: V2State) -> BlueprintFormalization: ...


class AnthropicFormalizerLLM:
    """production impl — Opus + structured output. lazy import (test 는 mock)."""

    def __init__(self, model: str = FORMALIZER_MODEL) -> None:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatAnthropic(model_name=model, timeout=60, stop=None)
        prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM_PROMPT), ("user", "{user}")]
        )
        self._chain = (
            prompt | llm.with_structured_output(BlueprintFormalization)
        ).with_retry(stop_after_attempt=5, wait_exponential_jitter=True)

    def formalize(self, state: V2State) -> BlueprintFormalization:
        result = self._chain.invoke({"user": _build_user_prompt(state)})
        if not isinstance(result, BlueprintFormalization):
            msg = (
                f"with_structured_output 가 {type(result).__name__} 반환 — "
                "BlueprintFormalization 기대"
            )
            raise TypeError(msg)
        return result


def make_formalizer_node(
    llm: FormalizerLLM | None = None,
) -> Callable[[V2State], V2State]:
    """factory — frozen strategy → ProblemBlueprint freeze. test 는 mock 주입.

    알고리즘 결정 필드(reduction_core/composition/domain)는 ``state.strategy`` 에서
    구조적으로 carry-over → Formalizer 가 은닉 코어를 못 바꾼다 (freeze 규율).
    """
    resolved_llm: FormalizerLLM = (
        llm if llm is not None else AnthropicFormalizerLLM()
    )

    def node(state: V2State) -> V2State:
        strategy = state.strategy
        if strategy is None:
            msg = "formalizer requires state.strategy — strategist must run first"
            raise ValueError(msg)
        formalization = resolved_llm.formalize(state)
        blueprint = ProblemBlueprint(
            reduction_core=strategy.reduction_core,
            composition=strategy.composition,
            domain=strategy.domain,
            io_schema=formalization.io_schema,
            output_invariants=formalization.output_invariants,
        )
        return state.model_copy(update={"blueprint": blueprint})

    return node
