"""spec_bridge 노드 — frozen blueprint + narrative → ProblemSpec (v2 synthesis 통합 step1).

blueprint-first 모델링(strategy→blueprint→narrative)을 solver/executor 입력 계약
``ProblemSpec`` 으로 파생한다. 이로써 M2 full-mode synthesis(golden/brute fan-out →
differential reconcile → 검증)를 v2 에서 재사용할 토대가 된다.

**sample expected 는 golden 실행으로** (사용자 원칙, RFC §7 — 정답은 golden 부트스트랩):
LLM 은 sample **input 만** 저작하고 expected 는 손계산하지 않는다 (N 큰 입출력은 스크립트/
golden 으로, 약점 저격 TC 만 LLM 예외). node 가 expected 를 비우고, reconcile 뒤
``sample_filler`` 노드가 canonical golden 실행으로 채운다. 이로써 LLM 직접 토큰 expected
생성 + ``sample_mismatch``(손계산 오답) 결함을 동시 제거. golden 정확성은 golden↔brute
differential + symbolic 이 보장.

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
SPEC_BRIDGE_TEMPERATURE = 0.2  # sample input 형식 준수 (발산 금지)


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
- sample_testcases: 3~5개. **input_text 만 작성하고 expected_output 은 빈 문자열("")**
  로 둔다 — 정답은 하류에서 검증된 golden 실행으로 자동 채운다 (직접 계산 금지:
  LLM 손계산은 토큰 낭비이자 오답[sample_mismatch]의 원인).
  - input_text 는 '입력 형식 (동결)' 규약을 **정확히** 준수 — 줄 구성/헤더/필드 순서/
    인덱싱까지. 생성기와 golden 파서가 이 규약 하나를 본다 (가장 중요).
  - **유일답 보장** (정답이 여럿이면 verifier/differential 가 false-reject) —
    작고 명백한 인스턴스로.
  - composition 이 비어있지 않으면 샘플은 **최소 규모**로 (정점 3~5, 간선 2~6 수준).

핵심: expected 는 golden 이 채우므로 **input 의 형식 정합성과 유일답 보장**에만 집중.

구조 주의 (tool schema 검증에서 거부되는 흔한 오류 — 재시도 전멸 시 전체 실패):
- io_contract 는 **중첩 객체**다: {{"input_format": "...", "output_format": "..."}} —
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
                # 정답은 golden 실행으로 (사용자 원칙) — LLM 이 무엇을 넣든 expected
                # 를 비우고 input 만 살린다. 하류 sample_filler 가 canonical golden
                # 으로 채운다 (freeze 규율: LLM 손계산 expected 를 못 끼워넣음).
                "sample_testcases": [
                    s.model_copy(update={"expected_output": ""})
                    for s in authored.sample_testcases
                ],
            }
        )
        return state.model_copy(update={"spec": spec})

    return node
