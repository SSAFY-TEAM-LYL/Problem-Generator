"""architect 노드 단위 테스트 — mock LLM 으로 LangChain 의존성 격리."""

from __future__ import annotations

from ipe.v1.nodes.architect import ArchitectLLM, make_architect_node
from ipe.v1.schema import (
    FailureMode,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    StructuredFeedback,
    TargetAlgorithm,
    TargetNode,
    VerificationResult,
)
from ipe.v1.state import V1State, initial_state


def _sample_spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="Mock shortest path",
        description="d",
        io_contract=IOContract(input_format="V E s t...", output_format="int"),
        sample_testcases=[
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
            SampleTestCase(input_text="3 2 0 2\n0 1 1\n1 2 2", expected_output="3"),
            SampleTestCase(input_text="2 0 0 1", expected_output="-1"),
        ],
    )


class _FixedSpecLLM:
    """ArchitectLLM Protocol impl — 항상 같은 ProblemSpec 반환."""

    def __init__(self, spec: ProblemSpec) -> None:
        self._spec = spec
        self.calls: list[V1State] = []

    def generate(self, state: V1State) -> ProblemSpec:
        self.calls.append(state)
        return self._spec


def test_architect_node_populates_spec_on_first_iteration() -> None:
    spec = _sample_spec()
    llm = _FixedSpecLLM(spec)
    node = make_architect_node(llm=llm)
    state = initial_state("run-001", TargetAlgorithm.DIJKSTRA)
    new_state = node(state)
    assert new_state is not state
    assert new_state.spec is spec
    assert len(llm.calls) == 1


def test_architect_node_passes_retry_feedback_in_state() -> None:
    """retry state 면 LLM 이 받은 state 에 verification.feedback 가 포함."""
    spec = _sample_spec()
    llm = _FixedSpecLLM(spec)
    node = make_architect_node(llm=llm)
    base = initial_state("run-001", TargetAlgorithm.DIJKSTRA)
    retry_state = base.model_copy(
        update={
            "iteration": 1,
            "verification": VerificationResult(
                overall_pass=False,
                failure_mode=FailureMode.SAMPLE_MISMATCH,
                feedback=StructuredFeedback(
                    target_node=TargetNode.ARCHITECT,
                    actionable_hint="너무 어려운 sample. 더 작게.",
                    blocking_signature="too-hard",
                ),
                iteration=0,
            ),
        }
    )
    node(retry_state)
    assert len(llm.calls) == 1
    passed_state = llm.calls[0]
    assert passed_state.verification is not None
    assert passed_state.verification.feedback is not None
    assert passed_state.verification.feedback.target_node is TargetNode.ARCHITECT


def test_architect_node_factory_uses_protocol_duck_typing() -> None:
    class _CustomLLM:
        def generate(self, state: V1State) -> ProblemSpec:
            return _sample_spec()

    custom: ArchitectLLM = _CustomLLM()
    node = make_architect_node(llm=custom)
    new_state = node(initial_state("r1", TargetAlgorithm.DIJKSTRA))
    assert new_state.spec is not None
    assert new_state.spec.target_algorithm is TargetAlgorithm.DIJKSTRA


def test_architect_node_immutable_state_transition() -> None:
    spec = _sample_spec()
    llm = _FixedSpecLLM(spec)
    node = make_architect_node(llm=llm)
    state = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    new_state = node(state)
    assert state.spec is None
    assert new_state.spec is spec
