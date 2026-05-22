"""designer 노드 단위 테스트 — mock LLM."""

from __future__ import annotations

import pytest

from ipe.v1.nodes.designer import (
    DIJKSTRA_DEFAULT_INVARIANTS,
    DesignerLLM,
    make_designer_node,
)
from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    Invariant,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    TargetAlgorithm,
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


def _dijkstra_design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Dijkstra",
        complexity_target=ComplexityBound(
            time_big_o="O((V+E) log V)", space_big_o="O(V+E)"
        ),
        pseudocode="Initialize dist[s]=0; priority queue; relax edges.",
        invariants=[
            Invariant(kind=kind, description=desc)
            for kind, desc in DIJKSTRA_DEFAULT_INVARIANTS
        ],
    )


class _FixedDesignLLM:
    """DesignerLLM Protocol impl."""

    def __init__(self, design: AlgorithmDesign) -> None:
        self._design = design
        self.calls: list[V1State] = []

    def generate(self, state: V1State) -> AlgorithmDesign:
        self.calls.append(state)
        return self._design


def _state_with_spec() -> V1State:
    base = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    return base.model_copy(update={"spec": _sample_spec()})


def test_designer_node_populates_design() -> None:
    design = _dijkstra_design()
    llm = _FixedDesignLLM(design)
    node = make_designer_node(llm=llm)
    state = _state_with_spec()
    new_state = node(state)
    assert new_state.design is design
    assert len(llm.calls) == 1


def test_designer_node_raises_when_spec_missing() -> None:
    """spec 없으면 designer 가 의미 없는 입력 — explicit error."""
    llm = _FixedDesignLLM(_dijkstra_design())
    node = make_designer_node(llm=llm)
    state = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    with pytest.raises(ValueError, match="state.spec"):
        node(state)


def test_dijkstra_default_invariants_have_4_kinds() -> None:
    """PR-A2 verifier 의 4 invariant_kind 와 1:1 매핑 확인."""
    kinds = {kind for kind, _ in DIJKSTRA_DEFAULT_INVARIANTS}
    assert kinds == {
        "non_negative_distance",
        "source_zero",
        "reachability_consistent",
        "shortest_distance_optimal",
    }


def test_designer_node_immutable_transition() -> None:
    design = _dijkstra_design()
    llm = _FixedDesignLLM(design)
    node = make_designer_node(llm=llm)
    state = _state_with_spec()
    new_state = node(state)
    assert state.design is None
    assert new_state.design is design


def test_designer_node_factory_uses_protocol() -> None:
    class _CustomLLM:
        def generate(self, state: V1State) -> AlgorithmDesign:
            return _dijkstra_design()

    custom: DesignerLLM = _CustomLLM()
    node = make_designer_node(llm=custom)
    state = _state_with_spec()
    new_state = node(state)
    assert new_state.design is not None
