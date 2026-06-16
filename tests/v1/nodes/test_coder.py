"""coder 노드 단위 테스트 — mock LLM + prompt rendering 검증."""

from __future__ import annotations

import pytest

from ipe.v1.nodes.coder import (
    _SYSTEM_PROMPT,
    _build_user_prompt,
    _coder_system_prompt,
    _coerce_parser_compliance,
    _parser_preamble_present,
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


# ---------- RTE 레버: canonical 파서 기계적 보장 (fail_synthesis 54% — #2 후속) ----------
# 진단: golden(sonnet)·brute(naive) 가 preamble 을 안 따라 자기 파서를 써서 동일 입력에
# IndexError. preamble 은 결정적이므로 '동일 입력+동일 preamble=동일 결과' — 기계적 강제 시
# 파싱 균일·정확. gate = preamble 미포함 시 교정 재생성, 끝까지 미준수면 best-effort(무회귀).


def test_parser_preamble_present_verbatim() -> None:
    preamble = "data = read()\nn = data[0]"
    assert _parser_preamble_present(preamble + "\nsolve(n)", preamble) is True


def test_parser_preamble_present_whitespace_insensitive() -> None:
    """모델이 들여쓰기/개행을 살짝 바꿔 복사해도 포함으로 인정 (공백 정규화)."""
    preamble = "data = read()\nn = data[0]"
    reflowed = "data  =  read()\n\n  n = data[0]\nsolve(n)"
    assert _parser_preamble_present(reflowed, preamble) is True


def test_parser_preamble_absent_returns_false() -> None:
    preamble = "data = read()\nn = data[0]"
    assert _parser_preamble_present("n = int(input())\nsolve(n)", preamble) is False


def test_parser_preamble_empty_always_present() -> None:
    """v1 canonical(preamble='') 은 규율 비대상 — 항상 통과(무회귀)."""
    assert _parser_preamble_present("anything at all", "") is True


def test_coerce_compliance_returns_first_when_present() -> None:
    """preamble 포함 시 재시도 없이 즉시 반환 (corrective 미주입)."""
    calls: list[str | None] = []

    def gen(corrective: str | None) -> SolutionAttempt:
        calls.append(corrective)
        return _attempt(code="MARK\nsolve()")

    out = _coerce_parser_compliance(gen, "MARK")
    assert out.code == "MARK\nsolve()"
    assert calls == [None]


def test_coerce_compliance_retries_then_succeeds() -> None:
    """1차 미포함 → 교정지시 붙여 재생성 → 2차 포함이면 그걸 반환."""
    seq = [_attempt(code="n=int(input())"), _attempt(code="MARK\nok")]
    calls: list[str | None] = []

    def gen(corrective: str | None) -> SolutionAttempt:
        calls.append(corrective)
        return seq[len(calls) - 1]

    out = _coerce_parser_compliance(gen, "MARK")
    assert out.code == "MARK\nok"
    assert len(calls) == 2
    assert calls[0] is None
    assert calls[1] is not None  # 2차에 교정지시 전달


def test_coerce_compliance_best_effort_after_max() -> None:
    """끝까지 미준수면 마지막 출력을 best-effort 로 반환 (현행 동작=무회귀)."""
    calls: list[str | None] = []

    def gen(corrective: str | None) -> SolutionAttempt:
        calls.append(corrective)
        return _attempt(code=f"own_parser_{len(calls)}")

    out = _coerce_parser_compliance(gen, "MARK", max_attempts=3)
    assert len(calls) == 3
    assert out.code == "own_parser_3"
