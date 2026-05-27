"""BinarySearchVerifier 단위 테스트 (D안 Phase 2b PR-C1).

variant: classic exact match (1-indexed, return idx or -1).
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
from ipe.v1.verifiers import BinarySearchVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N T + sorted ascending array (1-indexed)",
        output_format="1-indexed index or -1",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Binary Search",
        complexity_target=ComplexityBound(time_big_o="O(log N)", space_big_o="O(1)"),
        pseudocode="lo=1, hi=N, while lo<=hi: mid=(lo+hi)/2; ...",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.BINARY_SEARCH,
        title="Classic binary search",
        description="Find target in sorted array.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="5 7\n1 3 5 7 9", expected_output="4"),
            SampleTestCase(input_text="4 100\n1 2 3 4", expected_output="-1"),
            SampleTestCase(input_text="3 2\n2 2 2", expected_output="1"),
        ],
    )


def test_passes_with_golden_outputs() -> None:
    v = BinarySearchVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["4", "-1", "1"]
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert BinarySearchVerifier.target_algorithm is TargetAlgorithm.BINARY_SEARCH


def test_any_duplicate_position_accepted() -> None:
    v = BinarySearchVerifier()
    for idx in ["1", "2", "3"]:
        violations = v.verify(
            _spec_three_samples(),
            _design(),
            _attempt(),
            sample_outputs=["4", "-1", idx],
        )
        assert violations == [], f"idx={idx} should be valid"


def test_catches_garbage_output() -> None:
    v = BinarySearchVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["abc", "-1", "1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_format_valid"


def test_catches_zero_index() -> None:
    v = BinarySearchVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["0", "-1", "1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_format_valid"


def test_catches_negative_other_than_minus_one() -> None:
    v = BinarySearchVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["-5", "-1", "1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_format_valid"


def test_catches_index_out_of_range() -> None:
    v = BinarySearchVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["10", "-1", "1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "index_in_range"


def test_catches_wrong_value_at_idx() -> None:
    v = BinarySearchVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["1", "-1", "1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "value_matches_target_when_found"
    assert violations[0].evidence["value_at_idx"] == "1"


def test_catches_false_negative_when_target_exists() -> None:
    v = BinarySearchVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["-1", "-1", "1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "existence_consistent"


def test_target_at_first_or_last_position() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BINARY_SEARCH,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="5 1\n1 2 3 4 5", expected_output="1"),
            SampleTestCase(input_text="5 5\n1 2 3 4 5", expected_output="5"),
            SampleTestCase(input_text="5 3\n1 2 3 4 5", expected_output="3"),
        ],
    )
    v = BinarySearchVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["1", "5", "3"])
    assert violations == []


def test_negative_values_in_array() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BINARY_SEARCH,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="5 -3\n-10 -5 -3 0 7", expected_output="3"),
            SampleTestCase(input_text="3 0\n-1 0 1", expected_output="2"),
            SampleTestCase(input_text="2 5\n1 2", expected_output="-1"),
        ],
    )
    v = BinarySearchVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["3", "2", "-1"])
    assert violations == []


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BINARY_SEARCH,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3 2\n1 2 3", expected_output="2"),
            SampleTestCase(input_text="3 2\n1 2 3", expected_output="2"),
        ],
    )
    v = BinarySearchVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "1", "2"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "value_matches_target_when_found"


def test_count_engaged_all_parseable() -> None:
    assert BinarySearchVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_count_engaged_partial() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BINARY_SEARCH,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3 2\n1 2 3", expected_output="2"),
            SampleTestCase(input_text="bad N", expected_output="x"),
        ],
    )
    assert BinarySearchVerifier().count_engaged_samples(spec) == 1


def test_get_verifier_returns_binary_search_after_module_import() -> None:
    register_verifier(BinarySearchVerifier())
    verifier = get_verifier(TargetAlgorithm.BINARY_SEARCH)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.BINARY_SEARCH
