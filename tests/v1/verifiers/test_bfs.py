"""BFSVerifier 단위 테스트 (D안 Phase 2a PR-B4)."""

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
from ipe.v1.verifiers import BFSVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="V E s t + E directed edges (1-indexed)",
        output_format="single integer or -1",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="BFS",
        complexity_target=ComplexityBound(time_big_o="O(V+E)", space_big_o="O(V+E)"),
        pseudocode="queue + visited.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.BFS,
        title="Shortest edge count s->t",
        description="BFS on directed unweighted graph.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
            SampleTestCase(input_text="3 2 1 3\n1 2\n2 3", expected_output="2"),
            SampleTestCase(input_text="2 0 1 2", expected_output="-1"),
        ],
    )


def test_passes_with_golden_outputs() -> None:
    v = BFSVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["1", "2", "-1"]
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert BFSVerifier.target_algorithm is TargetAlgorithm.BFS


def test_catches_negative_distance() -> None:
    v = BFSVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["-2", "2", "-1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "non_negative_distance"


def test_catches_source_equals_target_nonzero() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BFS,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 2 2 2\n1 2\n2 3", expected_output="0"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
        ],
    )
    v = BFSVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["5", "1", "1"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "source_zero"


def test_catches_false_unreachable_claim() -> None:
    v = BFSVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["-1", "2", "-1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "reachability_consistent"


def test_catches_false_reachable_claim() -> None:
    v = BFSVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["1", "2", "1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "reachability_consistent"


def test_catches_suboptimal_distance() -> None:
    v = BFSVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["1", "99", "-1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "distance_optimal"
    assert violations[0].evidence["floyd_warshall_golden"] == "2"


def test_catches_shorter_than_optimal() -> None:
    v = BFSVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["1", "1", "-1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "distance_optimal"


def test_directed_edge_not_reversible() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BFS,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 1 2 1\n1 2", expected_output="-1"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
        ],
    )
    v = BFSVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["-1", "1", "1"])
    assert violations == []


def test_self_loop_does_not_create_distance_one_to_self() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BFS,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 1 1 1\n1 1", expected_output="0"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
        ],
    )
    v = BFSVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["0", "1", "1"])
    assert violations == []


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BFS,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
        ],
    )
    v = BFSVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["any", "99", "1"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "distance_optimal"


def test_zero_indexed_input_rejected() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BFS,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 1 0 1\n0 1", expected_output="x"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
        ],
    )
    v = BFSVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "1", "1"])
    assert violations == []


def test_count_engaged_all_parseable() -> None:
    assert BFSVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_count_engaged_partial() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BFS,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2 1 1 2\n1 2", expected_output="1"),
            SampleTestCase(input_text="bad header", expected_output="x"),
        ],
    )
    assert BFSVerifier().count_engaged_samples(spec) == 1


def test_get_verifier_returns_bfs_after_module_import() -> None:
    register_verifier(BFSVerifier())
    verifier = get_verifier(TargetAlgorithm.BFS)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.BFS
