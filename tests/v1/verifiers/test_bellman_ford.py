"""BellmanFordVerifier 단위 테스트 (D안 Phase 2c PR-D1)."""

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
from ipe.v1.verifiers import BellmanFordVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="V E s t + E edges (u v w) 1-indexed, w 음수 허용",
        output_format="single integer d[s][t], or -1 (unreachable)",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Bellman-Ford",
        complexity_target=ComplexityBound(time_big_o="O(VE)", space_big_o="O(V)"),
        pseudocode="Relax all edges V-1 times.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.BELLMAN_FORD,
        title="Bellman-Ford",
        description="shortest path with negative weights",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="4 5 1 4\n1 2 1\n2 3 -2\n3 4 1\n1 3 4\n2 4 5",
                expected_output="0",
            ),
            SampleTestCase(
                input_text="3 2 1 3\n1 2 5\n2 3 -3",
                expected_output="2",
            ),
            SampleTestCase(
                input_text="3 1 1 3\n1 2 1",
                expected_output="-1",
            ),
        ],
    )


def test_passes_with_correct_distances() -> None:
    v = BellmanFordVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["0", "2", "-1"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert BellmanFordVerifier.target_algorithm is TargetAlgorithm.BELLMAN_FORD


def test_catches_non_integer_output() -> None:
    v = BellmanFordVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["zero", "2", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_single_int"


def test_self_source_target_must_be_zero() -> None:
    v = BellmanFordVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BELLMAN_FORD,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1 1 1\n1 2 5", expected_output="0"),
            SampleTestCase(input_text="3 1 1 3\n1 2 5", expected_output="-1"),
            SampleTestCase(input_text="3 1 1 3\n1 2 5", expected_output="-1"),
        ],
    )
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=["5", "-1", "-1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "source_target_self_zero"


def test_catches_wrong_distance() -> None:
    v = BellmanFordVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["5", "2", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "distance_matches_floyd_warshall"
    assert violations[0].evidence["floyd_golden"] == "0"


def test_catches_false_negative_unreachable() -> None:
    v = BellmanFordVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["0", "-1", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "distance_matches_floyd_warshall"


def test_catches_false_positive_when_unreachable() -> None:
    v = BellmanFordVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["0", "2", "999"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "distance_matches_floyd_warshall"


def test_negative_cycle_silent_skip() -> None:
    """reachable negative cycle 이면 spec invalid → silent skip."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BELLMAN_FORD,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="3 3 1 3\n1 2 1\n2 3 -10\n3 1 1",
                expected_output="x",
            ),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    v = BellmanFordVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_unreachable_negative_cycle_not_skipped() -> None:
    """source 에서 unreachable 한 negative cycle 은 정상 처리."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BELLMAN_FORD,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="4 4 1 2\n1 2 5\n3 4 -10\n4 3 1\n2 1 0",
                expected_output="5",
            ),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    v = BellmanFordVerifier()
    assert v.count_engaged_samples(spec) == 3


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BELLMAN_FORD,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    v = BellmanFordVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_v_too_large_silent_skip() -> None:
    v_count = 35
    edges_text = "\n".join(f"{i + 1} {i + 2} 1" for i in range(v_count - 1))
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BELLMAN_FORD,
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
    v = BellmanFordVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert BellmanFordVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_get_verifier_returns_bellman_ford_after_module_import() -> None:
    register_verifier(BellmanFordVerifier())
    verifier = get_verifier(TargetAlgorithm.BELLMAN_FORD)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.BELLMAN_FORD


def test_classic_negative_edge_path_preferred() -> None:
    """1→2→3 path with weights 5, -2 = 3 (vs direct 1→3 = 10)."""
    v = BellmanFordVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BELLMAN_FORD,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="3 3 1 3\n1 2 5\n2 3 -2\n1 3 10",
                expected_output="3",
            ),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1 1 2\n1 2 5", expected_output="5"),
        ],
    )
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=["3", "5", "5"]
    )
    assert violations == []
