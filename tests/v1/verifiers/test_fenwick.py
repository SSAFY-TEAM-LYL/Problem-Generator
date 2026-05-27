"""FenwickVerifier 단위 테스트 (D안 Phase 2c PR-D5)."""

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
from ipe.v1.verifiers import FenwickVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N Q + array + Q ops (A i v | Q i)",
        output_format="Q op 마다 한 줄, prefix sum value",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Fenwick Tree",
        complexity_target=ComplexityBound(time_big_o="O(Q log N)", space_big_o="O(N)"),
        pseudocode="BIT: i += i & -i for update, i -= i & -i for prefix.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.FENWICK,
        title="Fenwick Tree",
        description="point-add + prefix-sum",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="5 4\n1 2 3 4 5\nQ 3\nA 2 10\nQ 5\nA 1 -3",
                expected_output="6\n25",
            ),
            SampleTestCase(
                input_text="3 3\n1 1 1\nQ 1\nQ 2\nQ 3",
                expected_output="1\n2\n3",
            ),
            SampleTestCase(
                input_text="4 2\n0 0 0 0\nA 4 5\nQ 4",
                expected_output="5",
            ),
        ],
    )


def test_passes_with_correct_prefix_sums() -> None:
    v = FenwickVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["6\n25", "1\n2\n3", "5"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert FenwickVerifier.target_algorithm is TargetAlgorithm.FENWICK


def test_catches_wrong_query_count() -> None:
    v = FenwickVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["6", "1\n2\n3", "5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_count_matches_queries"


def test_catches_non_integer_output() -> None:
    v = FenwickVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["six\ntwentyfive", "1\n2\n3", "5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_count_matches_queries"


def test_catches_wrong_prefix_sum() -> None:
    v = FenwickVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["7\n25", "1\n2\n3", "5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "prefix_sum_matches_naive"


def test_catches_negative_output_when_all_non_negative() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FENWICK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1\n1 2 3\nQ 3", expected_output="6"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 3", expected_output="6"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 3", expected_output="6"),
        ],
    )
    v = FenwickVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["-5", "6", "6"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "prefix_sum_non_negative_for_non_negative_input"


def test_negative_initial_values_supported() -> None:
    v = FenwickVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FENWICK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1\n-1 -2 -3\nQ 3", expected_output="-6"),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["-6", "3", "3"])
    assert violations == []


def test_only_adds_no_queries_empty_output() -> None:
    v = FenwickVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FENWICK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 2\n0 0 0\nA 1 5\nA 3 2", expected_output=""),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["", "3", "3"])
    assert violations == []


def test_add_then_query_same_index() -> None:
    v = FenwickVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FENWICK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="3 3\n0 0 0\nA 2 5\nQ 1\nQ 2",
                expected_output="0\n5",
            ),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["0\n5", "3", "3"])
    assert violations == []


def test_index_out_of_range_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FENWICK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1\n1 2 3\nQ 10", expected_output="x"),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
        ],
    )
    v = FenwickVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FENWICK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
        ],
    )
    v = FenwickVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_n_too_large_silent_skip() -> None:
    n_count = 1500
    arr_text = " ".join("0" for _ in range(n_count))
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FENWICK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text=f"{n_count} 1\n{arr_text}\nQ 1",
                expected_output="x",
            ),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
        ],
    )
    v = FenwickVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert FenwickVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_get_verifier_returns_fenwick_after_module_import() -> None:
    register_verifier(FenwickVerifier())
    verifier = get_verifier(TargetAlgorithm.FENWICK)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.FENWICK


def test_classic_textbook_array() -> None:
    """[3,2,-1,6,5,4,-3,3,7,2,3] prefix sums."""
    v = FenwickVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FENWICK,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="11 3\n3 2 -1 6 5 4 -3 3 7 2 3\nQ 5\nQ 8\nQ 11",
                expected_output="15\n19\n31",
            ),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
            SampleTestCase(input_text="3 1\n1 1 1\nQ 3", expected_output="3"),
        ],
    )
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=["15\n19\n31", "3", "3"]
    )
    assert violations == []
