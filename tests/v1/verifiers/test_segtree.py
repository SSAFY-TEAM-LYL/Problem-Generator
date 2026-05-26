"""SegmentTreeVerifier 단위 테스트 (D안 Phase 2a PR-B2 + PR-B2.1 format fix).

variant: Range Sum + Point Update.
Input format: "N Q" first line + array + Q ops (1-indexed).
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
from ipe.v1.verifiers import SegmentTreeVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N Q on first line, array, Q ops (U i v | Q l r) 1-indexed",
        output_format="one integer per Q op",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Segment Tree (Range Sum + Point Update)",
        complexity_target=ComplexityBound(
            time_big_o="O((N + Q) log N)", space_big_o="O(N)"
        ),
        pseudocode="build tree O(N); query/update O(log N).",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_basic() -> ProblemSpec:
    """N=5, arr=[1,2,3,4,5], 3 ops: Q 1 5, U 3 10, Q 1 5 → outputs 15, 22.

    1-indexed: U 3 10 means A[3]=10 (third element). Q 1 5 means sum(A[1..5]).
    """
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="Range sum with point updates",
        description="Segment tree.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="5 3\n1 2 3 4 5\nQ 1 5\nU 3 10\nQ 1 5",
                expected_output="15\n22",
            ),
            SampleTestCase(
                input_text="3 2\n10 20 30\nQ 2 3\nQ 1 1",
                expected_output="50\n10",
            ),
            SampleTestCase(
                input_text="4 3\n0 0 0 0\nU 1 5\nU 4 7\nQ 1 4",
                expected_output="12",
            ),
        ],
    )


# ---------- Pass paths ----------


def test_passes_with_golden_outputs() -> None:
    v = SegmentTreeVerifier()
    violations = v.verify(
        _spec_basic(),
        _design(),
        _attempt(),
        sample_outputs=["15\n22", "50\n10", "12"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert SegmentTreeVerifier.target_algorithm is TargetAlgorithm.SEGTREE
    assert SegmentTreeVerifier().target_algorithm is TargetAlgorithm.SEGTREE


# ---------- Invariant 1: output_count_matches_queries ----------


def test_catches_output_count_too_few() -> None:
    v = SegmentTreeVerifier()
    violations = v.verify(
        _spec_basic(), _design(), _attempt(), sample_outputs=["15", "50\n10", "12"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_count_matches_queries"
    assert violations[0].evidence["query_count"] == "2"


def test_catches_output_count_too_many() -> None:
    v = SegmentTreeVerifier()
    violations = v.verify(
        _spec_basic(),
        _design(),
        _attempt(),
        sample_outputs=["15\n22", "50\n10\n99", "12"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_count_matches_queries"


# ---------- Invariant 2: non_negative_sum_for_non_negative_input ----------


def test_catches_negative_sum_with_non_negative_input() -> None:
    v = SegmentTreeVerifier()
    violations = v.verify(
        _spec_basic(),
        _design(),
        _attempt(),
        sample_outputs=["-3\n22", "50\n10", "12"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "non_negative_sum_for_non_negative_input"


# ---------- Invariant 3: range_sum_optimal ----------


def test_catches_wrong_sum() -> None:
    v = SegmentTreeVerifier()
    violations = v.verify(
        _spec_basic(),
        _design(),
        _attempt(),
        sample_outputs=["99\n22", "50\n10", "12"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "range_sum_optimal"
    assert violations[0].evidence["naive_golden"] == "15"


def test_catches_wrong_sum_after_update() -> None:
    v = SegmentTreeVerifier()
    violations = v.verify(
        _spec_basic(),
        _design(),
        _attempt(),
        sample_outputs=["15\n17", "50\n10", "12"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "range_sum_optimal"
    assert violations[0].evidence["naive_golden"] == "22"


# ---------- Invariant 4: single_element_query_consistency ----------


def test_single_element_consistency() -> None:
    """sample 1 의 Q 1 1 (l==r) — array[0]=10 인데 99 출력 → range_sum 가 먼저 catch."""
    v = SegmentTreeVerifier()
    violations = v.verify(
        _spec_basic(),
        _design(),
        _attempt(),
        sample_outputs=["15\n22", "50\n99", "12"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "range_sum_optimal"


# ---------- Edge cases ----------


def test_empty_query_no_outputs() -> None:
    """update only, no Q ops → empty output."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="3 2\n1 2 3\nU 1 9\nU 2 8", expected_output=""
            ),
            SampleTestCase(
                input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"
            ),
            SampleTestCase(
                input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"
            ),
        ],
    )
    v = SegmentTreeVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["", "6", "6"])
    assert violations == []


def test_negative_update_value_passes_when_golden_matches() -> None:
    """LLM 의 자연 format 은 음수 update 허용 (U 1 -5)."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="1 3\n7\nQ 1 1\nU 1 -5\nQ 1 1",
                expected_output="7\n-5",
            ),
            SampleTestCase(
                input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"
            ),
            SampleTestCase(
                input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"
            ),
        ],
    )
    v = SegmentTreeVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["7\n-5", "6", "6"])
    assert violations == []


# ---------- Parse skip ----------


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"),
        ],
    )
    v = SegmentTreeVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["any", "99", "6"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "range_sum_optimal"


def test_invalid_op_kind_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1\n1 2 3\nX 1 3", expected_output="x"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"),
        ],
    )
    v = SegmentTreeVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "6", "6"])
    assert violations == []


def test_query_out_of_bounds_silent_skip() -> None:
    """Q 1 6 with N=3 → r>N fail → parse skip."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1\n1 2 3\nQ 1 6", expected_output="x"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"),
        ],
    )
    v = SegmentTreeVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "6", "6"])
    assert violations == []


def test_zero_indexed_input_rejected_as_out_of_range() -> None:
    """0-indexed input (i=0 또는 l=0) 는 1<=i<=N 위반 → parse skip."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1\n1 2 3\nQ 0 2", expected_output="x"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"),
        ],
    )
    v = SegmentTreeVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "6", "6"])
    assert violations == []


# ---------- count_engaged_samples ----------


def test_count_engaged_all_parseable() -> None:
    assert SegmentTreeVerifier().count_engaged_samples(_spec_basic()) == 3


def test_count_engaged_partial() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3 1\n1 2 3\nQ 1 3", expected_output="6"),
            SampleTestCase(input_text="X 0 2", expected_output="x"),
        ],
    )
    assert SegmentTreeVerifier().count_engaged_samples(spec) == 1


# ---------- Dispatch registry ----------


def test_get_verifier_returns_segtree_after_module_import() -> None:
    register_verifier(SegmentTreeVerifier())
    verifier = get_verifier(TargetAlgorithm.SEGTREE)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.SEGTREE
