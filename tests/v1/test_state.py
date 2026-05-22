"""V1State + initial_state factory 단위 테스트 (D안 PR-A3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    IOContract,
    IterationContext,
    ProblemSpec,
    SampleTestCase,
    TargetAlgorithm,
)
from ipe.v1.state import DEFAULT_MAX_ITERATIONS, V1State, initial_state


def test_initial_state_minimal_fields() -> None:
    state = initial_state("run-001", TargetAlgorithm.DIJKSTRA)
    assert state.run_id == "run-001"
    assert state.target_algorithm is TargetAlgorithm.DIJKSTRA
    assert state.iteration == 0
    assert state.max_iterations == DEFAULT_MAX_ITERATIONS
    assert state.spec is None
    assert state.design is None
    assert state.attempt is None
    assert state.verification is None
    assert state.final_status is None
    assert isinstance(state.context, IterationContext)
    assert state.context.run_id == "run-001"
    assert state.context.target_algorithm is TargetAlgorithm.DIJKSTRA


def test_initial_state_custom_max_iterations() -> None:
    state = initial_state("r1", TargetAlgorithm.DIJKSTRA, max_iterations=4)
    assert state.max_iterations == 4


def test_v1state_is_frozen() -> None:
    state = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    with pytest.raises(ValidationError):
        state.iteration = 5


def test_v1state_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        V1State.model_validate(
            {
                "run_id": "r1",
                "target_algorithm": "dijkstra",
                "context": IterationContext(
                    run_id="r1", target_algorithm=TargetAlgorithm.DIJKSTRA
                ).model_dump(),
                "unknown_field": "x",
            }
        )


def test_v1state_immutable_update_via_model_copy() -> None:
    state = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="t",
        description="d",
        io_contract=IOContract(input_format="i", output_format="o"),
        sample_testcases=[
            SampleTestCase(input_text="a", expected_output="b"),
            SampleTestCase(input_text="c", expected_output="d"),
            SampleTestCase(input_text="e", expected_output="f"),
        ],
    )
    new_state = state.model_copy(update={"spec": spec, "iteration": 1})
    assert new_state is not state
    assert state.spec is None
    assert state.iteration == 0
    assert new_state.spec is spec
    assert new_state.iteration == 1


def test_v1state_rejects_zero_max_iterations() -> None:
    with pytest.raises(ValidationError):
        V1State(
            run_id="r1",
            target_algorithm=TargetAlgorithm.DIJKSTRA,
            max_iterations=0,
            context=IterationContext(
                run_id="r1", target_algorithm=TargetAlgorithm.DIJKSTRA
            ),
        )


def test_v1state_rejects_negative_iteration() -> None:
    with pytest.raises(ValidationError):
        V1State(
            run_id="r1",
            target_algorithm=TargetAlgorithm.DIJKSTRA,
            iteration=-1,
            context=IterationContext(
                run_id="r1", target_algorithm=TargetAlgorithm.DIJKSTRA
            ),
        )


def test_v1state_accepts_partial_lazy_fields() -> None:
    """architect 후, design/attempt/verification 은 아직 None — 정상 partial state."""
    state = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="t",
        description="d",
        io_contract=IOContract(input_format="i", output_format="o"),
        sample_testcases=[
            SampleTestCase(input_text="a", expected_output="b"),
            SampleTestCase(input_text="c", expected_output="d"),
            SampleTestCase(input_text="e", expected_output="f"),
        ],
    )
    after_arch = state.model_copy(update={"spec": spec})
    assert after_arch.spec is not None
    assert after_arch.design is None
    assert after_arch.attempt is None


def test_v1state_final_status_literal_constraint() -> None:
    state = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    success_state = state.model_copy(update={"final_status": "success"})
    assert success_state.final_status == "success"
    # Pydantic v2 model_copy 는 update 값을 validation 안 함 — model_validate 로 강제
    with pytest.raises(ValidationError):
        V1State.model_validate(
            {**state.model_dump(), "final_status": "completed_ok"}
        )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Dijkstra",
        complexity_target=ComplexityBound(
            time_big_o="O((V+E) log V)", space_big_o="O(V+E)"
        ),
        pseudocode="dist[s]=0; pq; relax.",
    )


def test_v1state_accepts_design_assignment() -> None:
    """design 필드는 None 으로 시작, designer 노드 후 채워짐."""
    state = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    after = state.model_copy(update={"design": _design()})
    assert after.design is not None
    assert after.design.algorithm_name == "Dijkstra"
