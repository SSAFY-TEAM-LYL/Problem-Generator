"""TwoSumVerifier 단위 테스트 (D안 Phase 2a PR-B3).

Input format: "N T" first line + array (1-indexed).
Output: "i j" (1-indexed, i<j) 또는 "-1".
"""

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
from ipe.v1.verifiers import TwoSumVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N T on first line, array a_1..a_N (1-indexed)",
        output_format="'i j' (1-indexed, i<j) or '-1'",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Two Sum",
        complexity_target=ComplexityBound(time_big_o="O(N)", space_big_o="O(N)"),
        pseudocode="hash map: seen[T-a_i] returns idx.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    """3 samples:
    - sample 0: N=4 T=9, [2,7,11,15] → (1, 2)
    - sample 1: N=3 T=6, [3,2,4] → (2, 3)
    - sample 2: N=2 T=100, [1,2] → "-1"
    """
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="Two Sum",
        description="Find two indices whose values sum to T.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="4 9\n2 7 11 15", expected_output="1 2"),
            SampleTestCase(input_text="3 6\n3 2 4", expected_output="2 3"),
            SampleTestCase(input_text="2 100\n1 2", expected_output="-1"),
        ],
    )


# ---------- Pass paths ----------


def test_passes_with_golden_outputs() -> None:
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["1 2", "2 3", "-1"]
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert TwoSumVerifier.target_algorithm is TargetAlgorithm.TWO_SUM


# ---------- Invariant 1: output_format_valid ----------


def test_catches_garbage_output_format() -> None:
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["abc xyz", "2 3", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_format_valid"


def test_catches_three_tokens_output() -> None:
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 2 3", "2 3", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_format_valid"


def test_accepts_minus_one_for_no_pair() -> None:
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["1 2", "2 3", "-1"]
    )
    assert violations == []


# ---------- Invariant 2: indices_in_range_and_ordered ----------


def test_catches_index_out_of_range() -> None:
    """N=4 인데 5 출력."""
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 5", "2 3", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "indices_in_range_and_ordered"


def test_catches_i_greater_than_j() -> None:
    """j < i — order violation."""
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["2 1", "2 3", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "indices_in_range_and_ordered"


def test_catches_i_equals_j() -> None:
    """i == j — strict order required."""
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 1", "2 3", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "indices_in_range_and_ordered"


def test_catches_zero_index_rejected() -> None:
    """0-indexed → 1<=i 위반."""
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["0 1", "2 3", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "indices_in_range_and_ordered"


# ---------- Invariant 3: sum_equals_target ----------


def test_catches_wrong_pair_sum() -> None:
    """sample 0: N=4 T=9, [2,7,11,15]. (1,3) = 2+11 = 13 != 9."""
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 3", "2 3", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "sum_equals_target"
    assert violations[0].evidence["T"] == "9"


# ---------- Invariant 4: existence_consistent ----------


def test_catches_false_negative_when_pair_exists() -> None:
    """sample 0 has pair (1,2)=9, but LLM says '-1'."""
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["-1", "2 3", "-1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "existence_consistent"
    assert "brute_pair" in violations[0].evidence


def test_minus_one_when_no_pair_passes() -> None:
    """sample 2 has no pair, '-1' is correct."""
    v = TwoSumVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["1 2", "2 3", "-1"]
    )
    assert violations == []


# ---------- Edge cases ----------


def test_negative_values_in_array() -> None:
    """음수 허용. T=-1, [-3, 2, -2, 1] → (1,2)? a[1]+a[2]=-3+2=-1 ✓."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="4 -1\n-3 2 -2 1", expected_output="1 2"),
            SampleTestCase(input_text="3 0\n5 -5 1", expected_output="1 2"),
            SampleTestCase(input_text="2 100\n1 2", expected_output="-1"),
        ],
    )
    v = TwoSumVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["1 2", "1 2", "-1"])
    assert violations == []


# ---------- Parse skip ----------


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3 6\n3 2 4", expected_output="2 3"),
            SampleTestCase(input_text="3 6\n3 2 4", expected_output="2 3"),
        ],
    )
    v = TwoSumVerifier()
    # sample 0 skip. sample 1 actual=(1,2) → sum 3+2=5 != 6 → sum_equals_target.
    # sample 2 actual=(2,3) → valid → pass.
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["any", "1 2", "2 3"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "sum_equals_target"


def test_n_count_mismatch_silent_skip() -> None:
    """N=5 명시했는데 array 길이 4 → parse fail."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="5 6\n1 2 3 4", expected_output="x"),
            SampleTestCase(input_text="3 6\n3 2 4", expected_output="2 3"),
            SampleTestCase(input_text="3 6\n3 2 4", expected_output="2 3"),
        ],
    )
    v = TwoSumVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "2 3", "2 3"])
    assert violations == []


# ---------- count_engaged_samples ----------


def test_count_engaged_all_parseable() -> None:
    assert TwoSumVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_count_engaged_partial() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3 6\n3 2 4", expected_output="2 3"),
            SampleTestCase(input_text="bad N", expected_output="x"),
        ],
    )
    assert TwoSumVerifier().count_engaged_samples(spec) == 1


# ---------- Dispatch registry ----------


def test_get_verifier_returns_twosum_after_module_import() -> None:
    register_verifier(TwoSumVerifier())
    verifier = get_verifier(TargetAlgorithm.TWO_SUM)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.TWO_SUM
