"""generator_designer 노드 — frozen blueprint → GeneratorContract (M4 step2).

frozen blueprint(io_schema + reduction_core + output_invariants)을 받아 **입력 생성기
계약**(``GeneratorContract``: 규모 family + 엣지 케이스)을 LLM 으로 저작한다. 입력
*생성* 자체는 결정론(step3)이지만, **무엇을 생성할지의 전략**(어떤 규모 tier·엣지가
이 알고리즘의 정확성 채점에 중요한가)은 reduction_core 를 아는 LLM 이 설계한다
(RFC §4 — generator_contract 는 blueprint 의 일부, 형식 계약 author).

expected output 은 계약에 없음(순환 §7) — suite assembler(step4)가 verified golden
실행으로 채운다. carry-over 강제는 없음: scale_families/edge_cases 는 blueprint 의
기존 필드를 바꾸는 게 아니라 **새 생성 전략** 이라 freeze 충돌이 없다 (node 는 LLM
산출을 그대로 store). 단 field_bounds 는 io_schema field 이름을 따르도록 prompt 가
유도 (step3 생성기가 매칭) — 형식 enforce 는 후속(step3 검증).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ipe.v1.schema import GeneratorContract

from ..state import V2State

GENERATOR_DESIGNER_MODEL = "claude-opus-4-7"
GENERATOR_DESIGNER_TEMPERATURE = 0.2  # 형식 계약 설계 (발산 금지)


_SYSTEM_PROMPT = """\
당신은 algorithmic problem **test-suite 입력 생성 계약 설계자** 다. 이미 동결된 형식
계약(io_schema + 숨은 reduction_core + output_invariants)을 받아, 그 문제의 채점셋
입력을 어떻게 생성할지의 계약(GeneratorContract)을 설계한다.

typed GeneratorContract (구조화된 tool call) 로 반환:
- scale_families: 입력 규모 tier 들 (>=1). 각 ScaleFamily =
  - name: tier 이름 (예: 'small'/'medium'/'large'/'stress').
  - case_count: 이 tier 에서 생성할 케이스 수 (>0). small 은 손검증용 소수, large/
    stress 는 성능·정확성 경계용 더 많이.
  - field_bounds: 이 tier 의 per-field 크기/값 범위 (ConstraintRange list). **io_schema
    의 field 이름을 그대로** 쓰고, io_schema 의 전체 범위를 이 tier 로 **좁힌다**
    (절대 io_schema 상한을 넘기지 말 것). 비우면 io_schema 기본 범위.
  - description: 이 tier 가 무엇을 노리는지 한 줄.
- edge_cases: 반드시 포함할 경계/퇴화 입력들 (EdgeCaseSpec name + description). 이
  알고리즘에서 자주 틀리는 케이스 (예: 'empty'/'single'/'all_equal'/'disconnected'/
  'max_size'/'negative_zero_weights' 등 — reduction_core 에 맞게).
- determinism_seed: 보통 비워둔다 (생성기가 선택).
- notes: 생성 시 주의점 (선택).

규율:
- 알고리즘/형식을 **재결정하지 말 것** — io_schema/reduction_core 는 동결. 당신은
  '어떤 입력 분포·규모·엣지로 채점할지'의 생성 전략만 설계한다.
- field_bounds 는 io_schema 의 size_range/value_range 안에 있어야 한다 (초과 금지).
- 정확성 채점 강건성을 위해 small~large 규모 + 핵심 엣지를 고루 덮되, 과도한 case_count
  로 채점 비용을 폭증시키지 말 것 (tier 당 합리적 수).
"""


def _build_user_prompt(state: V2State) -> str:
    bp = state.blueprint
    if bp is None:
        msg = "generator_designer requires state.blueprint — formalizer must run first"
        raise ValueError(msg)
    fields = []
    for f in bp.io_schema.inputs:
        rng = ""
        if f.size_range is not None:
            rng += f" size[{f.size_range.min_value}..{f.size_range.max_value}]"
        if f.value_range is not None:
            rng += f" val[{f.value_range.min_value}..{f.value_range.max_value}]"
        fields.append(f"{f.name}:{f.type}{rng}")
    invariants = [f"{iv.kind}: {iv.description}" for iv in bp.output_invariants]
    return "\n".join(
        [
            f"reduction_core (숨은 알고리즘): {bp.reduction_core.value}",
            f"composition: {[a.value for a in bp.composition]}",
            f"domain: {bp.domain}",
            "",
            f"io_schema.inputs: {fields}",
            f"io_schema.output_type: {bp.io_schema.output_type}",
            f"io_schema.output_format: {bp.io_schema.output_format}",
            f"output_invariants: {invariants}",
        ]
    )


class GeneratorDesignerLLM(Protocol):
    """generator_designer 의 LLM dependency. test 가 mock 주입."""

    def design(self, state: V2State) -> GeneratorContract: ...


class AnthropicGeneratorDesignerLLM:
    """production impl — Opus + structured output. lazy import (test 는 mock)."""

    def __init__(self, model: str = GENERATOR_DESIGNER_MODEL) -> None:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatAnthropic(model_name=model, timeout=60, stop=None)
        prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM_PROMPT), ("user", "{user}")]
        )
        self._chain = (
            prompt | llm.with_structured_output(GeneratorContract)
        ).with_retry(stop_after_attempt=5, wait_exponential_jitter=True)

    def design(self, state: V2State) -> GeneratorContract:
        result = self._chain.invoke({"user": _build_user_prompt(state)})
        if not isinstance(result, GeneratorContract):
            msg = (
                f"with_structured_output 가 {type(result).__name__} 반환 — "
                "GeneratorContract 기대"
            )
            raise TypeError(msg)
        return result


def make_generator_designer_node(
    llm: GeneratorDesignerLLM | None = None,
) -> Callable[[V2State], V2State]:
    """factory — frozen blueprint → GeneratorContract. test 는 mock 주입.

    생성 전략(scale_families/edge_cases)은 새 설계라 carry-over 강제가 없다 — node 는
    LLM 산출 계약을 ``generator_contract`` 채널에 그대로 store.
    """
    resolved_llm: GeneratorDesignerLLM = (
        llm if llm is not None else AnthropicGeneratorDesignerLLM()
    )

    def node(state: V2State) -> V2State:
        if state.blueprint is None:
            msg = "generator_designer requires state.blueprint"
            raise ValueError(msg)
        contract = resolved_llm.design(state)
        return state.model_copy(update={"generator_contract": contract})

    return node
