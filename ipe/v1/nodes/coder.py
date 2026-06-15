"""coder 노드 — ProblemSpec + AlgorithmDesign + IterationContext → SolutionAttempt.

LLM: Opus 4.7. ``with_structured_output(SolutionAttempt)`` — typed deserialize.

D안 핵심:
- H1 (structured routing): prev verification.feedback (target_node enum +
  blocking_signature) 를 prompt 에 JSON-형식으로 명시 → fix 방향이 결정론적.
- H3 (skill amnesia 완화): IterationContext.accumulated_lessons + failed_strategies
  를 prompt 에 누적. signature dedup 으로 같은 lesson 반복 회피.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol

from ..schema import SolutionAttempt
from ..state import V1State

CODER_MODEL = "claude-opus-4-7"
CODER_TEMPERATURE = 0.2


_SYSTEM_PROMPT = """\
당신은 expert competitive programmer 다. 주어진 ProblemSpec + AlgorithmDesign 에
대해 typed SolutionAttempt (구조화된 tool call) 를 반환한다.

요구사항:
- code: 완전한 python solution (stdin 으로 input 읽고 stdout 으로 output 출력).
- language: "python" (Phase 1 기본).
- iteration: 입력으로 받은 iteration 값.
- lessons: 이 시도에서 학습한 lessons 의 list (signature + content + from_iter).
  prev IterationContext 의 lessons 와 중복되지 않게 (signature dedup 의무).
- brute_code: optional — small N stress 용 naive O(N^2)/O(2^N) impl. 있으면 R15
  cross-check anchor.

prev verification.feedback 가 있으면:
- failure_mode + invariant_violations + actionable_hint 를 정확히 반영해 새 code.
- 같은 blocking_signature 반복 회피 (oscillation 방지).
- accumulated_lessons 와 failed_strategies 를 참고해 같은 실수 회피.
"""


# v2 synthesis 전용 입력 파싱 규율 (opt-in). 골든/brute 코더가 같은 입력을 같게
# 읽어야 reconcile 합의 → 출하. 배치 진단상 array/value 시드 출하의 1위 병목이
# "양쪽 비-reference 코더 동시 IndexError"(파서 불일치)였다. literal 중괄호 금지
# (ChatPromptTemplate 변수 해석 — test_prompt_template_integrity 게이트).
_PARSE_DISCIPLINE = """
입력 파싱 규율 (골든·brute 가 같은 입력을 같게 읽어야 reconcile 합의 — 파서 불일치=RTE 거부):
- user 메시지에 '입력 파싱 preamble (필수)' 코드 블록이 주어지면, 그것을 **code 의 맨 앞에
  토씨 하나 바꾸지 말고 그대로** 두고, preamble 이 바인딩한 필드 변수로 알고리즘을 작성한다.
  **직접 stdin 파서를 작성하지 말 것** — preamble 이 형식의 단일 진실원천이다. 이로써 골든·
  brute 가 입력을 같게 소비해 IndexError(후행 스칼라 오소비)·중복카운트 오독이 사라진다.
- preamble 이 없을 때만(fallback) stdin 전체를 평탄 토큰 리스트로 읽어(data =
  sys.stdin.buffer.read().split()) io_contract.input_format 의 필드 순서대로만 소비한다.
"""


def _coder_system_prompt(parse_discipline: bool) -> str:
    """coder system prompt — ``parse_discipline`` 시 입력 파싱 규율을 append.

    v1 ``make_coder_node`` 는 기본 off 로 ``_SYSTEM_PROMPT`` 동결 유지(91.2% anchor
    자산); v2 synthesis(골든/brute)는 on 으로 파서 불일치 RTE(IndexError) 거부를 줄인다.
    """
    if parse_discipline:
        return _SYSTEM_PROMPT + _PARSE_DISCIPLINE
    return _SYSTEM_PROMPT


def _render_lessons(state: V1State) -> str:
    lessons = state.context.accumulated_lessons
    if not lessons:
        return ""
    lines = ["accumulated_lessons (signature dedup 누적):"]
    for i, lesson in enumerate(lessons, start=1):
        lines.append(f"  {i}. [{lesson.signature}] {lesson.content}")
    return "\n".join(lines)


def _render_failed_strategies(state: V1State) -> str:
    strategies = state.context.failed_strategies
    if not strategies:
        return ""
    lines = ["failed_strategies (다음 시도에서 회피):"]
    for s in strategies:
        lines.append(
            f"  - [{s.signature}] {s.description} "
            f"(mode={s.failure_mode.value}, iter={s.occurred_at_iter})"
        )
    return "\n".join(lines)


def _render_prev_verification(state: V1State) -> str:
    v = state.verification
    if v is None or v.feedback is None:
        return ""
    payload = {
        "iteration": v.iteration,
        "failure_mode": v.failure_mode.value,
        "samples_engaged": v.samples_engaged,
        "invariant_violations": [
            {
                "invariant_kind": iv.invariant_kind,
                "description": iv.description,
                "evidence": iv.evidence,
            }
            for iv in v.invariant_violations
        ],
        "feedback": {
            "target_node": v.feedback.target_node.value,
            "actionable_hint": v.feedback.actionable_hint,
            "blocking_signature": v.feedback.blocking_signature,
        },
    }
    return (
        "prev verification (structured JSON):\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
    )


def _render_prev_attempt(state: V1State) -> str:
    if state.attempt is None:
        return ""
    return (
        "prev attempt code (수정 대상):\n```python\n"
        + state.attempt.code
        + "\n```"
    )


def _build_user_prompt(state: V1State) -> str:
    spec = state.spec
    design = state.design
    if spec is None or design is None:
        msg = "coder requires state.spec and state.design — earlier nodes must run first"
        raise ValueError(msg)

    parts = [
        f"target_algorithm: {state.target_algorithm.value}",
        f"iteration: {state.iteration}",
        "",
        f"problem title: {spec.title}",
        f"description: {spec.description}",
        f"io_contract.input_format: {spec.io_contract.input_format}",
        f"io_contract.output_format: {spec.io_contract.output_format}",
        f"time_limit_ms: {spec.time_limit_ms}, memory_limit_mb: {spec.memory_limit_mb}",
        "",
        f"algorithm: {design.algorithm_name}",
        f"complexity_target: time={design.complexity_target.time_big_o}, "
        f"space={design.complexity_target.space_big_o}",
        f"pseudocode: {design.pseudocode}",
        f"required invariants: {[i.kind for i in design.invariants]}",
        "",
        "sample testcases (input → expected):",
    ]
    for i, sample in enumerate(spec.sample_testcases):
        parts.append(f"  [{i}] input:\n{sample.input_text}")
        parts.append(f"      expected: {sample.expected_output!r}")

    if spec.input_parser_code:
        parts.append("")
        parts.append(
            "입력 파싱 preamble (필수 — code 맨 앞에 그대로 두고, 바인딩된 변수로 풀 것):\n"
            "```python\n" + spec.input_parser_code + "\n```"
        )

    for extra in (
        _render_lessons(state),
        _render_failed_strategies(state),
        _render_prev_verification(state),
        _render_prev_attempt(state),
    ):
        if extra:
            parts.append("")
            parts.append(extra)
    return "\n".join(parts)


class CoderLLM(Protocol):
    """coder 의 LLM dependency."""

    def generate(self, state: V1State) -> SolutionAttempt: ...


class AnthropicCoderLLM:
    """production impl — Opus + structured output."""

    def __init__(
        self, model: str = CODER_MODEL, *, parse_discipline: bool = False
    ) -> None:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatAnthropic(model_name=model, timeout=60, stop=None)
        prompt = ChatPromptTemplate.from_messages(
            [("system", _coder_system_prompt(parse_discipline)), ("user", "{user}")]
        )
        self._chain = (
            prompt | llm.with_structured_output(SolutionAttempt)
        ).with_retry(stop_after_attempt=5, wait_exponential_jitter=True)

    def generate(self, state: V1State) -> SolutionAttempt:
        result = self._chain.invoke({"user": _build_user_prompt(state)})
        if not isinstance(result, SolutionAttempt):
            msg = (
                f"with_structured_output 가 {type(result).__name__} 반환 — "
                "SolutionAttempt 기대"
            )
            raise TypeError(msg)
        return result


def make_coder_node(
    llm: CoderLLM | None = None,
) -> Callable[[V1State], V1State]:
    resolved_llm: CoderLLM = llm if llm is not None else AnthropicCoderLLM()

    def node(state: V1State) -> V1State:
        if state.spec is None or state.design is None:
            msg = "coder requires state.spec and state.design"
            raise ValueError(msg)
        attempt = resolved_llm.generate(state)
        return state.model_copy(update={"attempt": attempt})

    return node
