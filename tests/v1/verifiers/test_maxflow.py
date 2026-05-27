"""MaxFlowVerifier 단위 테스트 (D안 Phase 2b PR-C7)."""

from __future__ import annotations

from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    TargetAlgorithm,
)
from ipe.v1.verifiers import MaxFlowVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="V E s t + E edges (u v c) 1-indexed",
        output_format="single integer — maximum flow s→t",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Edmonds-Karp",
        complexity_target=ComplexityBound(
            time_big_o="O(VE^2)", space_big_o="O(V+E)"
        ),
        pseudocode="BFS augmenting path, residual graph.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.MAX_FLOW,
        title="Maximum Flow",
        description="s→t max flow.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="4 5 1 4\n1 2 10\n1 3 5\n2 3 15\n2 4 10\n3 4 10",
                expected_output="15",
            ),
            SampleTestCase(
                input_text="2 1 1 2\n1 2 7",
                expected_output="7",
            ),
            SampleTestCase(
                input_text="3 2 1 3\n1 2 5\n2 3 3",
                expected_output="3",
            ),
        ],
    )


def test_passes_with_optimal_flows() -> None:
    v = MaxFlowVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["15", "7", "3"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert MaxFlowVerifier.target_algorithm is TargetAlgorithm.MAX_FLOW


def test_catches_non_integer_output() -> None:
    v = MaxFlowVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["fifteen", "7", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_single_int"


def test_catches_negative_flow() -> None:
    v = MaxFlowVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["-1", "7", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "flow_non_negative"


def test_catches_flow_above_source_outflow() -> None:
    v = MaxFlowVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["100", "7", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "flow_within_source_outflow"


def test_catches_suboptimal_flow() -> None:
    v = MaxFlowVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["10", "7", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "flow_matches_brute_min_cut"
    assert violations[0].evidence["brute_min_cut"] == "15"


def test_disconnected_source_sink_returns_zero() -> None:
    v = MaxFlowVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.MAX_FLOW,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1 1 3\n1 2 5", expected_output="0"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["0", "5", "5"])
    assert violations == []


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.MAX_FLOW,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    v = MaxFlowVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_s_equals_t_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.MAX_FLOW,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 1 1 1\n1 2 5", expected_output="x"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    v = MaxFlowVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_negative_capacity_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.MAX_FLOW,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 1 1 2\n1 2 -5", expected_output="x"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    v = MaxFlowVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_v_too_large_silent_skip() -> None:
    """V > 14 → brute 안전 상한 초과 → skip."""
    v_count = 20
    edges_text = "\n".join(f"{i + 1} {i + 2} 1" for i in range(v_count - 1))
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.MAX_FLOW,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text=f"{v_count} {v_count - 1} 1 {v_count}\n{edges_text}",
                expected_output="x",
            ),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    v = MaxFlowVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert MaxFlowVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_get_verifier_returns_maxflow_after_module_import() -> None:
    register_verifier(MaxFlowVerifier())
    verifier = get_verifier(TargetAlgorithm.MAX_FLOW)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.MAX_FLOW


def test_parallel_edges_supported() -> None:
    """Parallel edges (multi-graph): cut capacity sums all parallel caps."""
    v = MaxFlowVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.MAX_FLOW,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="2 3 1 2\n1 2 3\n1 2 4\n1 2 2",
                expected_output="9",
            ),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["9", "5", "5"])
    assert violations == []


def test_diamond_graph_classic() -> None:
    """4-node diamond: 1→2,3 → 4."""
    v = MaxFlowVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.MAX_FLOW,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="4 4 1 4\n1 2 5\n1 3 5\n2 4 5\n3 4 5",
                expected_output="10",
            ),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=["10", "5", "5"]
    )
    assert violations == []
