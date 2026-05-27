"""CoinChangeVerifier 단위 테스트 (D안 Phase 2c PR-D6)."""

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
from ipe.v1.verifiers import CoinChangeVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N A + N coins (c_i >= 1)",
        output_format="single int — min coin count, or -1 if impossible",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Coin Change",
        complexity_target=ComplexityBound(time_big_o="O(N*A)", space_big_o="O(A)"),
        pseudocode="dp[i] = min(dp[i-c]+1 for c in coins if c<=i).",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.COIN_CHANGE,
        title="Coin Change",
        description="min coins",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 11\n1 2 5", expected_output="3"),
            SampleTestCase(input_text="1 3\n2", expected_output="-1"),
            SampleTestCase(input_text="3 0\n1 2 5", expected_output="0"),
        ],
    )


def test_passes_with_optimal_counts() -> None:
    v = CoinChangeVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["3", "-1", "0"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert CoinChangeVerifier.target_algorithm is TargetAlgorithm.COIN_CHANGE


def test_catches_non_integer_output() -> None:
    v = CoinChangeVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["three", "-1", "0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_single_int"


def test_catches_count_above_amount() -> None:
    v = CoinChangeVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["20", "-1", "0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "count_in_valid_range"


def test_catches_false_negative_impossible() -> None:
    v = CoinChangeVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["-1", "-1", "0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "existence_consistent_with_dp"


def test_catches_false_positive_when_impossible() -> None:
    """sample 1: A=3 coin=[2] impossible. output=1 in valid range, existence triggers."""
    v = CoinChangeVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["3", "1", "0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "existence_consistent_with_dp"


def test_catches_suboptimal_count() -> None:
    v = CoinChangeVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["7", "-1", "0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "count_matches_dp_optimal"
    assert violations[0].evidence["dp_golden"] == "3"


def test_zero_amount_returns_zero() -> None:
    v = CoinChangeVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.COIN_CHANGE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 0\n1 5 10", expected_output="0"),
            SampleTestCase(input_text="1 0\n7", expected_output="0"),
            SampleTestCase(input_text="2 0\n3 4", expected_output="0"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["0"] * 3)
    assert violations == []


def test_zero_coin_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.COIN_CHANGE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 5\n0 3", expected_output="x"),
            SampleTestCase(input_text="2 5\n1 3", expected_output="3"),
            SampleTestCase(input_text="2 5\n1 3", expected_output="3"),
        ],
    )
    v = CoinChangeVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.COIN_CHANGE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2 5\n1 3", expected_output="3"),
            SampleTestCase(input_text="2 5\n1 3", expected_output="3"),
        ],
    )
    v = CoinChangeVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_a_too_large_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.COIN_CHANGE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 5000\n1 2", expected_output="x"),
            SampleTestCase(input_text="2 5\n1 3", expected_output="3"),
            SampleTestCase(input_text="2 5\n1 3", expected_output="3"),
        ],
    )
    v = CoinChangeVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert CoinChangeVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_get_verifier_returns_coin_change_after_module_import() -> None:
    register_verifier(CoinChangeVerifier())
    verifier = get_verifier(TargetAlgorithm.COIN_CHANGE)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.COIN_CHANGE


def test_classic_us_coins() -> None:
    """[1, 5, 10, 25] for amount 30 = 25+5 = 2 coins."""
    v = CoinChangeVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.COIN_CHANGE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="4 30\n1 5 10 25", expected_output="2"),
            SampleTestCase(input_text="4 40\n1 5 10 25", expected_output="3"),
            SampleTestCase(input_text="4 7\n1 5 10 25", expected_output="3"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["2", "3", "3"])
    assert violations == []


def test_unbounded_use_supported() -> None:
    """1 coin of value 1 for amount 5 = 5 coins (unbounded)."""
    v = CoinChangeVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.COIN_CHANGE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="1 5\n1", expected_output="5"),
            SampleTestCase(input_text="1 10\n2", expected_output="5"),
            SampleTestCase(input_text="1 100\n10", expected_output="10"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["5", "5", "10"])
    assert violations == []
