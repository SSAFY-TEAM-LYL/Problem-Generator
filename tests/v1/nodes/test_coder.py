"""coder 노드 단위 테스트 — mock LLM + prompt rendering 검증."""

from __future__ import annotations

import pytest

from ipe.v1.nodes.coder import (
    _SYSTEM_PROMPT,
    _build_user_prompt,
    _coder_system_prompt,
    make_coder_node,
)
from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    FailureMode,
    Invariant,
    IOContract,
    Lesson,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    StructuredFeedback,
    TargetAlgorithm,
    TargetNode,
    VerificationResult,
)
from ipe.v1.state import V1State, initial_state


def _spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="t",
        description="d",
        io_contract=IOContract(input_format="V E s t...", output_format="int"),
        sample_testcases=[
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
            SampleTestCase(input_text="3 2 0 2\n0 1 1\n1 2 2", expected_output="3"),
            SampleTestCase(input_text="2 0 0 1", expected_output="-1"),
        ],
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Dijkstra",
        complexity_target=ComplexityBound(
            time_big_o="O((V+E) log V)", space_big_o="O(V+E)"
        ),
        pseudocode="dist[s]=0; pq; relax.",
        invariants=[
            Invariant(kind="non_negative_distance", description="d>=0"),
        ],
    )


def _attempt(code: str = "print(5)") -> SolutionAttempt:
    return SolutionAttempt(code=code, iteration=0)


class _FixedAttemptLLM:
    def __init__(self, attempt: SolutionAttempt) -> None:
        self._attempt = attempt
        self.calls: list[V1State] = []

    def generate(self, state: V1State) -> SolutionAttempt:
        self.calls.append(state)
        return self._attempt


def _state_with_spec_design() -> V1State:
    return initial_state("r1", TargetAlgorithm.DIJKSTRA).model_copy(
        update={"spec": _spec(), "design": _design()}
    )


def test_coder_node_populates_attempt() -> None:
    attempt = _attempt()
    llm = _FixedAttemptLLM(attempt)
    node = make_coder_node(llm=llm)
    state = _state_with_spec_design()
    new_state = node(state)
    assert new_state.attempt is attempt
    assert len(llm.calls) == 1


def test_coder_node_raises_when_spec_or_design_missing() -> None:
    llm = _FixedAttemptLLM(_attempt())
    node = make_coder_node(llm=llm)
    with pytest.raises(ValueError, match="state.spec and state.design"):
        node(initial_state("r1", TargetAlgorithm.DIJKSTRA))
    only_spec = initial_state("r1", TargetAlgorithm.DIJKSTRA).model_copy(
        update={"spec": _spec()}
    )
    with pytest.raises(ValueError, match="state.spec and state.design"):
        node(only_spec)


def test_prompt_includes_lessons_when_present() -> None:
    state = _state_with_spec_design()
    ctx = state.context.append_lesson(
        Lesson(signature="use-heapq", content="Use heapq for PQ.", from_iter=0)
    )
    state = state.model_copy(update={"context": ctx})
    prompt = _build_user_prompt(state)
    assert "use-heapq" in prompt
    assert "Use heapq for PQ." in prompt


def test_prompt_includes_structured_feedback_when_present() -> None:
    state = _state_with_spec_design()
    v = VerificationResult(
        overall_pass=False,
        failure_mode=FailureMode.INVARIANT_VIOLATION,
        feedback=StructuredFeedback(
            target_node=TargetNode.CODER,
            actionable_hint="Verify dist[] init.",
            blocking_signature="shortest_distance_optimal-violated",
        ),
        iteration=1,
    )
    state = state.model_copy(update={"verification": v})
    prompt = _build_user_prompt(state)
    assert '"failure_mode": "invariant_violation"' in prompt
    assert '"target_node": "coder"' in prompt
    assert "Verify dist[] init." in prompt


def test_prompt_includes_prev_attempt_code_when_present() -> None:
    state = _state_with_spec_design().model_copy(
        update={"attempt": _attempt(code="prev_attempt_marker_xyz")}
    )
    prompt = _build_user_prompt(state)
    assert "prev_attempt_marker_xyz" in prompt
    assert "prev attempt code" in prompt


def test_prompt_omits_optional_sections_on_first_iter() -> None:
    state = _state_with_spec_design()
    prompt = _build_user_prompt(state)
    assert "accumulated_lessons" not in prompt
    assert "failed_strategies" not in prompt
    assert "prev verification" not in prompt
    assert "prev attempt code" not in prompt


def test_prompt_injects_parser_preamble_when_present() -> None:
    """#2: spec.input_parser_code 가 있으면 user 프롬프트에 필수 preamble 로 주입.

    synthesis 코더가 LLM 파서를 직접 쓰지 않고 이 결정적 preamble 을 받아 파서 분산을
    구조적으로 차단한다."""
    spec = _spec().model_copy(
        update={"input_parser_code": "PARSER_PREAMBLE_MARKER_xyz"}
    )
    state = _state_with_spec_design().model_copy(update={"spec": spec})
    prompt = _build_user_prompt(state)
    assert "PARSER_PREAMBLE_MARKER_xyz" in prompt
    assert "입력 파싱 preamble (필수" in prompt


def test_prompt_omits_parser_preamble_when_empty() -> None:
    """v1 canonical(input_parser_code='') 은 미주입 — 동결 prompt 무영향."""
    prompt = _build_user_prompt(_state_with_spec_design())
    assert "입력 파싱 preamble" not in prompt


def test_parse_discipline_opt_in_appends_parsing_rules() -> None:
    """v2 synthesis 는 파싱 규율 on — 골든·brute 가 동일 입력을 동일 파싱해야
    reconcile 합의(파서 불일치=양쪽 RTE IndexError 거부) 가 늘어난다."""
    disciplined = _coder_system_prompt(parse_discipline=True)
    assert "평탄 토큰" in disciplined
    assert "필드 순서" in disciplined
    assert "IndexError" in disciplined
    assert "단일 진실원천" in disciplined
    # 기존 _SYSTEM_PROMPT 를 보존한 채 규율을 append (대체 아님)
    assert disciplined.startswith(_SYSTEM_PROMPT)


def test_parse_discipline_off_preserves_frozen_v1_prompt() -> None:
    """기본 off — v1 make_coder_node 의 _SYSTEM_PROMPT 동결(91.2% anchor 자산) 보존."""
    assert _coder_system_prompt(parse_discipline=False) == _SYSTEM_PROMPT
    assert "평탄 토큰" not in _SYSTEM_PROMPT
