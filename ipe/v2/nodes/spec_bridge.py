"""spec_bridge 노드 — frozen blueprint + narrative → ProblemSpec (v2 synthesis 통합 step1).

blueprint-first 모델링(strategy→blueprint→narrative)을 solver/executor 입력 계약
``ProblemSpec`` 으로 파생한다. 이로써 M2 full-mode synthesis(golden/brute fan-out →
differential reconcile → 검증)를 v2 에서 재사용할 토대가 된다.

**approach (a)** (사용자 결정): LLM 이 ``sample_testcases`` 를 저작 (v1 architect 식).
expected 계산오류는 하류 synthesis(golden↔brute differential) + verification(M1 Tier B /
M2 reconcile) 가 catch — 기존 검증 해자가 안전망.

**freeze 규율** (step2~4 carry-over 와 동일): node 가 두 핵심 필드를 강제 carry-over —
- ``target_algorithm`` = ``blueprint.reduction_core`` (verifier dispatch, LLM 못 바꿈).
- ``description`` = ``narrative.scenario`` (faithfulness 검증된 은닉 지문, LLM 못 재작성).
LLM 은 title/io_contract/constraints/sample_testcases 만 저작 → 검증 체인 보존.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ipe.v1.schema import ProblemSpec

from ..state import V2State

SPEC_BRIDGE_MODEL = "claude-opus-4-7"
SPEC_BRIDGE_TEMPERATURE = 0.2  # sample expected 정확도 (발산 금지)


_SYSTEM_PROMPT = """\
당신은 algorithmic problem spec author 다. 이미 동결된 형식 계약(io_schema +
output_invariants + 내부 reduction_core)과 은닉 지문(narrative)을 받아, solver 가
풀 ``ProblemSpec`` 을 저작한다.

typed ProblemSpec (구조화된 tool call) 로 반환:
- target_algorithm: 주어진 reduction_core enum value 그대로 (내부 verifier dispatch용 —
  node 가 어차피 강제하니 정확히 그 값으로).
- title: 도메인에 어울리는 한 줄 제목.
- description: 짧은 placeholder (node 가 narrative 로 대체하니 1줄이면 충분).
- io_contract: io_schema 의 input/output 형식과 **정확히 일치**하는 input_format /
  output_format (간결, 한 줄씩).
- constraints: io_schema 의 size_range/value_range 를 ConstraintRange list 로.
- sample_testcases: 3~5개. **reduction_core 알고리즘으로 직접 계산한 정확한 expected**.
  - io_contract 입출력 형식을 정확히 준수.
  - **유일답 보장** (정답이 여럿이면 verifier/differential 가 false-reject) —
    작은 인스턴스로 손계산 가능하게.
  - expected 를 단계별로 직접 계산 (어림짐작 금지).

핵심: sample 의 expected 정확도가 중요하나, 틀려도 하류 synthesis/verification 이
catch 하므로 **불확실하면 더 작고 명백한 인스턴스**로 작성.
"""


def _build_user_prompt(state: V2State) -> str:
    bp = state.blueprint
    nar = state.narrative
    if bp is None or nar is None:
        msg = "spec_bridge requires state.blueprint and state.narrative"
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
            f"reduction_core (target_algorithm): {bp.reduction_core.value}",
            f"composition: {[a.value for a in bp.composition]}",
            f"domain: {bp.domain}",
            "",
            f"io_schema.inputs: {fields}",
            f"io_schema.output_type: {bp.io_schema.output_type}",
            f"io_schema.output_format: {bp.io_schema.output_format}",
            f"output_invariants: {invariants}",
            "",
            "narrative (은닉 지문 — 이 문제를 푸는 것):",
            nar.scenario,
        ]
    )


class SpecBridgeLLM(Protocol):
    """spec_bridge 의 LLM dependency. test 가 mock 주입."""

    def author(self, state: V2State) -> ProblemSpec: ...


class AnthropicSpecBridgeLLM:
    """production impl — Opus + structured output. lazy import (test 는 mock)."""

    def __init__(self, model: str = SPEC_BRIDGE_MODEL) -> None:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatAnthropic(model_name=model, timeout=60, stop=None)
        prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM_PROMPT), ("user", "{user}")]
        )
        self._chain = (prompt | llm.with_structured_output(ProblemSpec)).with_retry(
            stop_after_attempt=5, wait_exponential_jitter=True
        )

    def author(self, state: V2State) -> ProblemSpec:
        result = self._chain.invoke({"user": _build_user_prompt(state)})
        if not isinstance(result, ProblemSpec):
            msg = (
                f"with_structured_output 가 {type(result).__name__} 반환 — "
                "ProblemSpec 기대"
            )
            raise TypeError(msg)
        return result


def make_spec_bridge_node(
    llm: SpecBridgeLLM | None = None,
) -> Callable[[V2State], V2State]:
    """factory — blueprint+narrative → ProblemSpec. test 는 mock 주입.

    ``target_algorithm``/``description`` 은 blueprint/narrative 에서 강제 carry-over →
    LLM 이 verifier dispatch 와 은닉 지문을 못 바꾼다 (freeze 규율, 검증 체인 보존).
    """
    resolved_llm: SpecBridgeLLM = (
        llm if llm is not None else AnthropicSpecBridgeLLM()
    )

    def node(state: V2State) -> V2State:
        bp = state.blueprint
        nar = state.narrative
        if bp is None or nar is None:
            msg = "spec_bridge requires state.blueprint and state.narrative"
            raise ValueError(msg)
        authored = resolved_llm.author(state)
        spec = authored.model_copy(
            update={
                "target_algorithm": bp.reduction_core,
                "description": nar.scenario,
            }
        )
        return state.model_copy(update={"spec": spec})

    return node
