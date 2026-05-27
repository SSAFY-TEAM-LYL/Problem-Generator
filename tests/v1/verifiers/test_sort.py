"""SortVerifier 단위 테스트 (D안 Phase 2b PR-C5)."""

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
from ipe.v1.verifiers import SortVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N + a_1 ... a_N (1-indexed)",
        output_format="b_1 ... b_N — sorted ascending",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Quicksort",
        complexity_target=ComplexityBound(
            time_big_o="O(N log N)", space_big_o="O(log N)"
        ),
        pseudocode="Hoare/Lomuto partition + recursive.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.SORT,
        title="Comparison Sort",
        description="Sort ascending.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="5\n3 1 4 1 5", expected_output="1 1 3 4 5"),
            SampleTestCase(input_text="4\n-2 -5 3 0", expected_output="-5 -2 0 3"),
            SampleTestCase(input_text="3\n7 7 7", expected_output="7 7 7"),
        ],
    )


def test_passes_with_sorted_outputs() -> None:
    v = SortVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 1 3 4 5", "-5 -2 0 3", "7 7 7"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert SortVerifier.target_algorithm is TargetAlgorithm.SORT


def test_catches_length_mismatch() -> None:
    v = SortVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 1 3 4", "-5 -2 0 3", "7 7 7"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_length_matches_n"


def test_catches_multiset_mismatch() -> None:
    v = SortVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["0 0 0 0 0", "-5 -2 0 3", "7 7 7"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_preserves_input_multiset"


def test_catches_not_sorted() -> None:
    v = SortVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["3 1 1 4 5", "-5 -2 0 3", "7 7 7"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_sorted_ascending"


def test_negative_integers_supported() -> None:
    v = SortVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3\n-1 -2 -3", expected_output="-3 -2 -1"),
            SampleTestCase(input_text="3\n-1 -2 -3", expected_output="-3 -2 -1"),
            SampleTestCase(input_text="3\n-1 -2 -3", expected_output="-3 -2 -1"),
        ],
    )
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=["-3 -2 -1"] * 3
    )
    assert violations == []


def test_empty_input_supported() -> None:
    v = SortVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="0", expected_output=""),
            SampleTestCase(input_text="1\n42", expected_output="42"),
            SampleTestCase(input_text="2\n2 1", expected_output="1 2"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["", "42", "1 2"])
    assert violations == []


def test_whitespace_tolerant_multiline_output() -> None:
    v = SortVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1\n1\n3\n4\n5", "-5\n-2\n0\n3", "7\n7\n7"],
    )
    assert violations == []


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2\n2 1", expected_output="1 2"),
            SampleTestCase(input_text="2\n2 1", expected_output="1 2"),
        ],
    )
    v = SortVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "1 2", "1 2"])
    assert violations == []
    assert v.count_engaged_samples(spec) == 2


def test_mismatched_n_silent_skip() -> None:
    """N=5 라 했는데 실제 3개만 → parse fail → skip."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="5\n1 2 3", expected_output="x"),
            SampleTestCase(input_text="2\n2 1", expected_output="1 2"),
            SampleTestCase(input_text="2\n2 1", expected_output="1 2"),
        ],
    )
    v = SortVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert SortVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_count_engaged_partial() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3\n1 2 3", expected_output="1 2 3"),
            SampleTestCase(input_text="bad N", expected_output="x"),
        ],
    )
    assert SortVerifier().count_engaged_samples(spec) == 1


def test_get_verifier_returns_sort_after_module_import() -> None:
    register_verifier(SortVerifier())
    verifier = get_verifier(TargetAlgorithm.SORT)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.SORT


def test_already_sorted_input() -> None:
    v = SortVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="5\n1 2 3 4 5", expected_output="1 2 3 4 5"),
            SampleTestCase(input_text="5\n1 2 3 4 5", expected_output="1 2 3 4 5"),
            SampleTestCase(input_text="5\n1 2 3 4 5", expected_output="1 2 3 4 5"),
        ],
    )
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=["1 2 3 4 5"] * 3
    )
    assert violations == []


def test_reverse_sorted_input() -> None:
    v = SortVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="5\n5 4 3 2 1", expected_output="1 2 3 4 5"),
            SampleTestCase(input_text="5\n5 4 3 2 1", expected_output="1 2 3 4 5"),
            SampleTestCase(input_text="5\n5 4 3 2 1", expected_output="1 2 3 4 5"),
        ],
    )
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=["1 2 3 4 5"] * 3
    )
    assert violations == []
