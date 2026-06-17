"""채점셋 확장 — LLM 다양 입력 생성 + verified golden oracle 로 assemble.

hybrid/canonical 브리지의 핵심 보강. **문제**: v1 그래프(canonical/full)는 풀 채점셋
노드가 없어 ``test_suite`` 가 sample(3~5) 뿐 → 채점 강건성 부족. **해법**: v1 spec
(input_format + constraints + samples)을 본 LLM 으로 규모·엣지가 다양한 raw 입력을
생성하고, **이미 검증된 golden** 을 oracle 로 실행해 expected 를 채워(``assemble_suite``
재사용) 풀 채점셋을 만든다.

왜 v2 결정론 input_gen(``generate_inputs``)을 안 쓰나
-----------------------------------------------------
그 엔진은 v2 **canonical 직렬화**로 입력을 만드는데(io_schema 기반), hybrid golden 은
v1 의 **자유형식 ``input_format``** 에 맞춰 작성돼 파서 규약이 다르다. 직렬화↔파서
불일치는 silent 하게 assembled ratio 0.0 을 낳는다(M4 dijkstra anchor 로 실증된 결함).
그래서 LLM 이 v1 ``input_format`` 을 직접 보고 생성하고, golden 이 실제로 파싱 못하는
입력은 ``assemble_suite`` 가 drop 한다. samples 는 golden 이 이미 통과시킨(v1 verification)
입력이라 **최소 생존선** — 전부-drop(ValueError)을 구조적으로 막는다.

determinism
-----------
LLM 생성이라 v2 결정론 엔진만큼 재현적이진 않다(temperature 낮춤). assemble 단계는
(입력, golden) 고정이면 결정론. 이 타협은 'v1 golden 재사용'의 직접 귀결이다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field

from ipe.v1.schema import GeneratedTestCase, ProblemSpec, TestSuite
from ipe.v2.generation.assembler import assemble_suite

if TYPE_CHECKING:
    from ipe.v1.verification._exec import CodeRunner

GRADING_INPUT_GEN_MODEL = "claude-sonnet-4-6"
GRADING_INPUT_GEN_TEMPERATURE = 0.3  # 형식 준수하되 입력 분포는 다양하게
DEFAULT_TARGET_COUNT = 24  # 생성 요청 입력 수 (drop 후 samples 와 합쳐 풀셋)


class GradingInputGeneratorLLM(Protocol):
    """다양 입력 생성 LLM dependency — expected 없는 pending 케이스. test 가 mock 주입."""

    def generate(
        self, spec: ProblemSpec, *, target_count: int
    ) -> tuple[GeneratedTestCase, ...]: ...


def expand_grading_suite(
    spec: ProblemSpec,
    golden_code: str,
    *,
    generator: GradingInputGeneratorLLM,
    runner: CodeRunner,
    golden_origin: str = "golden",
    target_count: int = DEFAULT_TARGET_COUNT,
) -> TestSuite:
    """samples + LLM 생성 입력 → golden 실행 expected 채움 → assembled 풀 채점셋.

    samples 를 pending 에 항상 포함한다 — golden 이 파싱 보장(v1 검증 통과)이라
    ``assemble_suite`` 의 전부-drop(ValueError)을 막는 최소 생존선. 생성 입력 중 golden
    이 못 푸는 것(형식 불일치)은 drop. 반환 suite 는 ``is_assembled``(모든 expected 채움)
    이고 각 케이스에 ``golden_elapsed_ms``(백엔드 TL 산정 근거)가 채워진다.
    """
    sample_cases = tuple(
        GeneratedTestCase(input_text=s.input_text, category="sample")
        for s in spec.sample_testcases
    )
    generated = generator.generate(spec, target_count=target_count)
    pending = TestSuite(cases=sample_cases + tuple(generated))
    return assemble_suite(
        pending, golden_code, runner=runner, golden_origin=golden_origin
    )


# --------------------------------------------------------------------------- #
# production LLM impl — v1 input_format 을 본 다양 입력 생성 (Sonnet, structured)     #
# --------------------------------------------------------------------------- #


class _RawInput(BaseModel):
    """LLM 이 채우는 입력 1건 — expected/golden_elapsed 는 LLM 이 만들지 않는다."""

    input_text: str = Field(..., description="input_format 을 정확히 따르는 입력 원문")
    category: str = Field(..., description="규모/엣지 태그 (예: 'large'/'edge_empty')")


class _RawInputBatch(BaseModel):
    """LLM structured output 묶음 — 다양 입력 케이스들."""

    cases: list[_RawInput] = Field(default_factory=list)


_INPUT_GEN_SYSTEM = """\
당신은 알고리즘 문제의 **채점셋 입력 생성기** 다. 주어진 문제의 ``input_format`` 을
**글자 그대로** 따르는 다양한 입력을 생성한다. expected output 은 만들지 않는다 —
검증된 golden 이 실행으로 채운다.

typed 산출(구조화된 tool call)로 입력 케이스 목록을 반환:
- 각 케이스 = ``input_text`` (형식 준수 입력 원문) + ``category`` (출처 태그).
- category 예: 'small'/'medium'/'large'/'stress' (규모) · 'edge_empty'/'edge_single'/
  'edge_max'/'edge_boundary' (경계·퇴화). 규모와 엣지를 고루 덮어라.

규율:
- ``input_format`` 의 줄 구성·구분자·필드 순서를 정확히 지킨다. 형식을 벗어난 입력은
  golden 이 읽지 못해 버려진다(낭비).
- ``constraints`` 범위 **안에서만** 생성하되, 상한/하한 경계를 엣지로 적극 포함한다.
- 정답이나 출력 형식을 추측하지 마라 — 입력만 만든다.
- large/stress 로 성능 경계도 덮되, 과도한 거대 입력으로 채점 비용을 폭증시키지 마라.
"""


def _build_input_gen_prompt(spec: ProblemSpec, target_count: int) -> str:
    constraints = (
        ", ".join(
            f"{c.name} ∈ [{c.min_value}, {c.max_value}]" for c in spec.constraints
        )
        or "(미명시)"
    )
    samples = "\n".join(
        f"  형식예시: {s.input_text!r}" for s in spec.sample_testcases[:3]
    )
    return "\n".join(
        [
            f"title: {spec.title}",
            f"description:\n{spec.description}",
            f"input_format:\n{spec.io_contract.input_format}",
            f"constraints: {constraints}",
            f"샘플 입력(형식 참고용):\n{samples}",
            "",
            f"위 input_format 을 정확히 따르는 입력을 약 {target_count}개 생성하라 "
            "(규모 small~large + 핵심 엣지를 고루 덮어).",
        ]
    )


class AnthropicGradingInputGeneratorLLM:
    """production impl — Sonnet + structured output. lazy import (test 는 mock)."""

    def __init__(self, model: str = GRADING_INPUT_GEN_MODEL) -> None:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatAnthropic(
            model_name=model,
            temperature=GRADING_INPUT_GEN_TEMPERATURE,
            timeout=90,
            stop=None,
        )
        prompt = ChatPromptTemplate.from_messages(
            [("system", _INPUT_GEN_SYSTEM), ("user", "{user}")]
        )
        self._chain = (prompt | llm.with_structured_output(_RawInputBatch)).with_retry(
            stop_after_attempt=5, wait_exponential_jitter=True
        )

    def generate(
        self, spec: ProblemSpec, *, target_count: int
    ) -> tuple[GeneratedTestCase, ...]:
        result = self._chain.invoke(
            {"user": _build_input_gen_prompt(spec, target_count)}
        )
        if not isinstance(result, _RawInputBatch):
            msg = (
                f"with_structured_output 가 {type(result).__name__} 반환 — "
                "_RawInputBatch 기대"
            )
            raise TypeError(msg)
        return tuple(
            GeneratedTestCase(input_text=c.input_text, category=c.category or "generated")
            for c in result.cases
            if c.input_text.strip()  # 빈 입력 방지 (input_text min_length=1 보존)
        )
