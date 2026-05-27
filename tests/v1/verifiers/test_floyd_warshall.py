"""FloydWarshallVerifier 단위 테스트 (D안 Phase 2c PR-D2)."""

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
from ipe.v1.verifiers import FloydWarshallVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="V E + E edges (u v w) 1-indexed, w 음수 허용",
        output_format="V lines × V tokens — d[i][j] matrix, -1 if unreachable",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Floyd-Warshall",
        complexity_target=ComplexityBound(time_big_o="O(V^3)", space_big_o="O(V^2)"),
        pseudocode="Triple loop: dp[i][j] = min(dp[i][j], dp[i][k] + dp[k][j]).",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.FLOYD_WARSHALL,
        title="Floyd-Warshall",
        description="all-pairs shortest path",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="3 3\n1 2 5\n2 3 -2\n1 3 10",
                expected_output="0 5 3\n-1 0 -2\n-1 -1 0",
            ),
            SampleTestCase(
                input_text="2 1\n1 2 7",
                expected_output="0 7\n-1 0",
            ),
            SampleTestCase(
                input_text="3 0",
                expected_output="0 -1 -1\n-1 0 -1\n-1 -1 0",
            ),
        ],
    )


def test_passes_with_correct_matrix() -> None:
    v = FloydWarshallVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=[
            "0 5 3\n-1 0 -2\n-1 -1 0",
            "0 7\n-1 0",
            "0 -1 -1\n-1 0 -1\n-1 -1 0",
        ],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert FloydWarshallVerifier.target_algorithm is TargetAlgorithm.FLOYD_WARSHALL


def test_catches_non_matrix_output() -> None:
    v = FloydWarshallVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=[
            "garbage",
            "0 7\n-1 0",
            "0 -1 -1\n-1 0 -1\n-1 -1 0",
        ],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_v_by_v_matrix"


def test_catches_non_zero_diagonal() -> None:
    v = FloydWarshallVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=[
            "1 5 3\n-1 0 -2\n-1 -1 0",
            "0 7\n-1 0",
            "0 -1 -1\n-1 0 -1\n-1 -1 0",
        ],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "diagonal_is_zero"


def test_catches_wrong_distance() -> None:
    v = FloydWarshallVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=[
            "0 5 10\n-1 0 -2\n-1 -1 0",
            "0 7\n-1 0",
            "0 -1 -1\n-1 0 -1\n-1 -1 0",
        ],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "matches_bellman_ford_golden"


def test_correct_chain_distances() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FLOYD_WARSHALL,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="3 2\n1 2 1\n2 3 1",
                expected_output="0 1 2\n-1 0 1\n-1 -1 0",
            ),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0 5\n-1 0"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0 5\n-1 0"),
        ],
    )
    v = FloydWarshallVerifier()
    violations = v.verify(
        spec,
        _design(),
        _attempt(),
        sample_outputs=[
            "0 1 2\n-1 0 1\n-1 -1 0",
            "0 5\n-1 0",
            "0 5\n-1 0",
        ],
    )
    assert violations == []


def test_negative_cycle_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FLOYD_WARSHALL,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="3 3\n1 2 1\n2 3 -10\n3 1 1",
                expected_output="x",
            ),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0 5\n-1 0"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0 5\n-1 0"),
        ],
    )
    v = FloydWarshallVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FLOYD_WARSHALL,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0 5\n-1 0"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0 5\n-1 0"),
        ],
    )
    v = FloydWarshallVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_v_too_large_silent_skip() -> None:
    v_count = 30
    edges_text = "\n".join(f"{i + 1} {i + 2} 1" for i in range(v_count - 1))
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FLOYD_WARSHALL,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text=f"{v_count} {v_count - 1}\n{edges_text}",
                expected_output="x",
            ),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0 5\n-1 0"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0 5\n-1 0"),
        ],
    )
    v = FloydWarshallVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_matrix_parse_flat_tokens() -> None:
    """V*V tokens single line, split lines, individual tokens 모두 허용."""
    v = FloydWarshallVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FLOYD_WARSHALL,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0 5 -1 0"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0 5\n-1 0"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="0\n5\n-1\n0"),
        ],
    )
    violations = v.verify(
        spec,
        _design(),
        _attempt(),
        sample_outputs=["0 5 -1 0", "0 5\n-1 0", "0\n5\n-1\n0"],
    )
    assert violations == []


def test_count_engaged_all_parseable() -> None:
    assert FloydWarshallVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_get_verifier_returns_floyd_warshall_after_module_import() -> None:
    register_verifier(FloydWarshallVerifier())
    verifier = get_verifier(TargetAlgorithm.FLOYD_WARSHALL)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.FLOYD_WARSHALL


def test_unreachable_returns_negative_one() -> None:
    v = FloydWarshallVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=[
            "0 5 3\n-1 0 -2\n100 100 0",
            "0 7\n-1 0",
            "0 -1 -1\n-1 0 -1\n-1 -1 0",
        ],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "matches_bellman_ford_golden"
