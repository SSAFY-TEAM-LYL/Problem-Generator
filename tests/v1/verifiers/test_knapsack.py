"""KnapsackVerifier 단위 테스트 (D안 Phase 2b PR-C4)."""

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
from ipe.v1.verifiers import KnapsackVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N C + N lines of 'w_i v_i', 1-indexed",
        output_format="single integer — maximum value",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="0/1 Knapsack",
        complexity_target=ComplexityBound(time_big_o="O(N*C)", space_big_o="O(N*C)"),
        pseudocode="DP: dp[i][c] = max(dp[i-1][c], dp[i-1][c-w_i]+v_i).",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.KNAPSACK,
        title="0/1 Knapsack",
        description="Max value subset.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="3 5\n2 3\n3 4\n4 5",
                expected_output="7",
            ),
            SampleTestCase(
                input_text="4 10\n5 10\n4 40\n6 30\n3 50",
                expected_output="90",
            ),
            SampleTestCase(
                input_text="2 0\n1 100\n1 200",
                expected_output="0",
            ),
        ],
    )


def test_passes_with_optimal_values() -> None:
    v = KnapsackVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["7", "90", "0"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert KnapsackVerifier.target_algorithm is TargetAlgorithm.KNAPSACK


def test_catches_non_integer_output() -> None:
    v = KnapsackVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["seven", "90", "0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_single_int"


def test_catches_negative_value() -> None:
    v = KnapsackVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["-3", "90", "0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "value_non_negative"


def test_catches_value_above_total() -> None:
    v = KnapsackVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["13", "90", "0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "value_within_total_bound"


def test_catches_suboptimal_value() -> None:
    v = KnapsackVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["6", "90", "0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "value_optimal_via_brute"
    assert violations[0].evidence["brute_optimal"] == "7"


def test_zero_capacity_returns_zero() -> None:
    v = KnapsackVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KNAPSACK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 0\n1 100\n2 200\n3 300", expected_output="0"),
            SampleTestCase(input_text="2 0\n1 1\n2 2", expected_output="0"),
            SampleTestCase(input_text="1 0\n5 99", expected_output="0"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["0", "0", "0"])
    assert violations == []


def test_capacity_exceeds_all_items_returns_sum() -> None:
    v = KnapsackVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KNAPSACK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 100\n2 3\n3 4\n4 5", expected_output="12"),
            SampleTestCase(input_text="2 100\n1 1\n2 2", expected_output="3"),
            SampleTestCase(input_text="1 100\n5 99", expected_output="99"),
        ],
    )
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=["12", "3", "99"]
    )
    assert violations == []


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KNAPSACK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2 5\n1 1\n2 2", expected_output="3"),
            SampleTestCase(input_text="2 5\n1 1\n2 2", expected_output="3"),
        ],
    )
    v = KnapsackVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "3", "3"])
    assert violations == []


def test_negative_weight_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KNAPSACK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="1 5\n-1 10", expected_output="x"),
            SampleTestCase(input_text="2 5\n1 1\n2 2", expected_output="3"),
            SampleTestCase(input_text="2 5\n1 1\n2 2", expected_output="3"),
        ],
    )
    v = KnapsackVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_n_too_large_silent_skip() -> None:
    """N > 22 (brute 안전 상한 초과) → verifier silent skip."""
    n = 25
    items_text = "\n".join("1 1" for _ in range(n))
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KNAPSACK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text=f"{n} 100\n{items_text}", expected_output="x"),
            SampleTestCase(input_text="2 5\n1 1\n2 2", expected_output="3"),
            SampleTestCase(input_text="2 5\n1 1\n2 2", expected_output="3"),
        ],
    )
    v = KnapsackVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert KnapsackVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_count_engaged_partial() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KNAPSACK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2 5\n1 1\n2 2", expected_output="3"),
            SampleTestCase(input_text="bad N", expected_output="x"),
        ],
    )
    assert KnapsackVerifier().count_engaged_samples(spec) == 1


def test_get_verifier_returns_knapsack_after_module_import() -> None:
    register_verifier(KnapsackVerifier())
    verifier = get_verifier(TargetAlgorithm.KNAPSACK)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.KNAPSACK


def test_classic_knapsack_textbook_case() -> None:
    """4-item, capacity 8: items=[(2,3),(3,4),(4,5),(5,6)], opt=10."""
    v = KnapsackVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KNAPSACK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="4 8\n2 3\n3 4\n4 5\n5 6",
                expected_output="10",
            ),
            SampleTestCase(input_text="2 5\n1 1\n2 2", expected_output="3"),
            SampleTestCase(input_text="2 5\n1 1\n2 2", expected_output="3"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["10", "3", "3"])
    assert violations == []
