"""spec_bridge 노드 — frozen blueprint + narrative → ProblemSpec (v2 synthesis 통합 step1).

blueprint-first 모델링(strategy→blueprint→narrative)을 solver/executor 입력 계약
``ProblemSpec`` 으로 파생한다. 이로써 M2 full-mode synthesis(golden/brute fan-out →
differential reconcile → 검증)를 v2 에서 재사용할 토대가 된다.

**approach (a)** (사용자 결정): LLM 이 ``sample_testcases`` 를 저작 (v1 architect 식).
expected 계산오류는 하류 synthesis(golden↔brute differential) + verification(M1 Tier B /
M2 reconcile) 가 catch — 기존 검증 해자가 안전망.

**freeze 규율** (step2~4 carry-over 와 동일): node 가 세 핵심 필드를 강제 carry-over —
- ``target_algorithm`` = ``blueprint.reduction_core`` (verifier dispatch, LLM 못 바꿈).
- ``description`` = ``narrative.scenario`` (faithfulness 검증된 은닉 지문, LLM 못 재작성).
- ``io_contract`` = **canonical 렌더** (M4 step6): ``input_format`` 은 io_schema 에서
  ``render_input_format`` 으로 코드 렌더(입력 생성기의 직렬화와 동일 규약), ``output_
  format`` 은 ``io_schema.output_format`` carry-over. LLM prose 가 형식 계약을 정하면
  생성 입력과 golden 파서가 어긋난다 — dijkstra anchor ratio 0.0 으로 실증된 불일치의
  구조적 해소.
LLM 은 title/constraints/sample_testcases 만 실질 저작 → 검증 체인 보존.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ipe.v1.schema import IOContract, ProblemSpec

from ..generation.input_gen import render_input_format
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
- io_contract: user 메시지의 '입력 형식 (동결)' 텍스트를 input_format 에, io_schema.
  output_format 을 output_format 에 그대로 (node 가 어차피 canonical 로 강제한다).
- constraints: io_schema 의 size_range/value_range 를 ConstraintRange list 로.
- sample_testcases: 3~5개. **reduction_core 알고리즘으로 직접 계산한 정확한 expected**.
  - input_text 는 '입력 형식 (동결)' 규약을 **정확히** 준수 — 줄 구성/헤더/필드 순서/
    인덱싱까지. 생성기와 golden 파서가 이 규약 하나를 본다.
  - **유일답 보장** (정답이 여럿이면 verifier/differential 가 false-reject) —
    작은 인스턴스로 손계산 가능하게.
  - expected 를 단계별로 직접 계산 (어림짐작 금지).
  - composition 이 비어있지 않으면 expected 는 **합성된 출력 의미**로 계산한다 —
    reduction_core 정석 출력이 아니라 (예: 임계값 탐색 문제면 찾은 임계값이 답).
  - composition 이 비어있지 않으면 샘플은 **최소 규모**로 강제한다 (정점 3~5,
    간선 2~6 수준) — 합성 expected 의 손계산은 오류율이 높다. 각 샘플마다 합성
    절차를 단계별로 명시 수행해 **검산**할 것 (예: 후보 임계값마다 feasibility
    판정을 나열).

핵심: sample 의 expected 정확도가 중요하나, 틀려도 하류 synthesis/verification 이
catch 하므로 **불확실하면 더 작고 명백한 인스턴스**로 작성.

구조 주의 (tool schema 검증에서 거부되는 흔한 오류 — 재시도 전멸 시 전체 실패):
- io_contract 는 **중첩 객체**다: {"input_format": "...", "output_format": "..."} —
  문자열 하나로 넣지 말 것. output_format 은 io_contract **안**의 필드다 — 같은
  이름의 **최상위** 필드를 만들면 스키마에 없는 필드로 거부된다.
- sample_testcases 는 필수 필드 — **누락 금지** (한 개라도 반드시 채울 것).
- 스키마에 정의된 필드 외 임의 최상위 필드를 추가하지 말 것.
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
            "입력 형식 (동결 — sample input_text 는 반드시 이 형식):",
            render_input_format(bp.io_schema),
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
        try:
            authored = resolved_llm.author(state)
        except Exception as exc:  # noqa: BLE001 — LLM 신뢰성 가드 (graph crash 방지)
            # structured output 재시도 전멸(BS-run3 실측: pydantic ValidationError)이
            # graph 밖 crash 로 전파되던 것을 valid fail 종료로 회수. 예외 요약은
            # state 에 보존 (silent swallow 금지) — route_after_spec_bridge 가
            # spec 부재를 보고 fail_spec_authoring 으로 종료한다.
            error = f"{type(exc).__name__}: {exc}"
            return state.model_copy(update={"spec_authoring_error": error[:500]})
        spec = authored.model_copy(
            update={
                "target_algorithm": bp.reduction_core,
                "description": nar.scenario,
                # step6: 형식 계약은 코드가 정한다 — 입력 생성기와 동일 규약 렌더
                "io_contract": IOContract(
                    input_format=render_input_format(bp.io_schema),
                    output_format=bp.io_schema.output_format,
                ),
            }
        )
        return state.model_copy(update={"spec": spec})

    return node
