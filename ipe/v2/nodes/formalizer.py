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
- graph 입력은 **self-contained 단일 필드** 로 모델링한다 (weighted_edges/tree_edges
  는 V·E 헤더를 자체 포함 — 정점 수 V 를 별도 int 필드로 분리하지 말 것: 입력 생성기
  와 중복/모순을 만든다). 정점 수 범위는 그 graph 필드의 size_range 로 표현한다.
- 정점을 참조하는 스칼라 필드(출발/도착 s, t 등)의 value_range 는 graph 필드
  size_range 의 **하한 이내** 로 잡는다 (V 가 하한일 때도 유효한 정점이도록).
- io_schema 는 필드 집합이 **자기완결적 의미 정합**이어야 한다: 임계값/예산/필터
  같은 비교용 스칼라 필드는 그 **비교 대상**이 되는 per-element 데이터가 io_schema
  안에 실제로 존재할 때만 추가한다 (예: capacity_threshold 를 두려면 간선별 capacity
  가 입력에 있어야 한다 — 없으면 주어진 입력만으로 풀 수 없는 **고아 필드**가 된다).
  풀이에 역할이 없는 필드는 넣지 말 것.
- composition 이 비어있지 않으면 **합성이 필수**가 되도록 형식을 설계한다: 출력의
  의미가 reduction_core 의 정석 출력 그대로가 아니라, composition 기법을 거쳐야만
  계산되는 값이어야 한다 (예: binary_search 합성이면 reduction_core 를 feasibility
  판정으로 반복 호출해 찾는 최소/최대 임계값이 출력). 정석 출력에 장식만 더한 것은
  합성이 아니다 — 그런 문제는 고전 동형으로 QA 유출 게이트에서 reject 된다.
- graph 류 필드의 간선 속성은 **단일 가중치 w 하나뿐**이다 (weighted_edges 의
  canonical 직렬화 = 줄당 `u v w` — 간선당 추가 속성은 표현이 불가능하다). 간선
  **다속성**을 요구하는 설계(예: 손실+내경 두 값)는 금지. 필터/임계값류 합성은
  그 단일 w 에 대한 조건으로 설계한다 (예: 'w ≤ t 인 간선만 사용 가능할 때의
  최단 경로' — 임계값은 별도 스칼라 필드).
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
