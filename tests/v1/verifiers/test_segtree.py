"""SegmentTreeVerifier 단위 테스트 (D안 Phase 2a PR-B2).

variant: Range Sum + Point Update.
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
        input_format="N, array, Q, ops (U i v | Q l r)",
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
    """N=5, arr=[1,2,3,4,5], 3 ops: Q 0 4, U 2 10, Q 0 4 → outputs 15, 22."""
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="Range sum with point updates",
        description="Segment tree.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="5\n1 2 3 4 5\n3\nQ 0 4\nU 2 10\nQ 0 4",
                expected_output="15\n22",
            ),
            SampleTestCase(
                input_text="3\n10 20 30\n2\nQ 1 2\nQ 0 0",
                expected_output="50\n10",
            ),
            SampleTestCase(
                input_text="4\n0 0 0 0\n3\nU 0 5\nU 3 7\nQ 0 3",
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
    """sample 0 expects 2 query outputs but only 1 given."""
    v = SegmentTreeVerifier()
    violations = v.verify(
        _spec_basic(), _design(), _attempt(), sample_outputs=["15", "50\n10", "12"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_count_matches_queries"
    assert violations[0].evidence["query_count"] == "2"


def test_catches_output_count_too_many() -> None:
    """sample 1 expects 2 outputs but 3 given."""
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
    """all input >= 0, but LLM 이 negative sum 출력."""
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
    """sample 0 의 첫 query golden=15 인데 99 출력."""
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
    """sample 0 의 두 번째 query (update 후) golden=22 인데 17 출력."""
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
    """sample 1 의 Q 0 0 (l==r) 가 array[0]=10 인데 99 출력 → range_sum 가 먼저 catch."""
    v = SegmentTreeVerifier()
    violations = v.verify(
        _spec_basic(),
        _design(),
        _attempt(),
        sample_outputs=["15\n22", "50\n99", "12"],
    )
    # range_sum_optimal 이 먼저 priority (naive 와 다름 → 즉시 catch).
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
            SampleTestCase(input_text="3\n1 2 3\n2\nU 0 9\nU 1 8", expected_output=""),
            SampleTestCase(input_text="3\n1 2 3\n1\nQ 0 2", expected_output="6"),
            SampleTestCase(input_text="3\n1 2 3\n1\nQ 0 2", expected_output="6"),
        ],
    )
    v = SegmentTreeVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["", "6", "6"])
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
            SampleTestCase(input_text="3\n1 2 3\n1\nQ 0 2", expected_output="6"),
            SampleTestCase(input_text="3\n1 2 3\n1\nQ 0 2", expected_output="6"),
        ],
    )
    v = SegmentTreeVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["any", "99", "6"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "range_sum_optimal"


def test_invalid_op_kind_silent_skip() -> None:
    """unknown op kind 'X' → parse fail → skip."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3\n1 2 3\n1\nX 0 2", expected_output="x"),
            SampleTestCase(input_text="3\n1 2 3\n1\nQ 0 2", expected_output="6"),
            SampleTestCase(input_text="3\n1 2 3\n1\nQ 0 2", expected_output="6"),
        ],
    )
    v = SegmentTreeVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "6", "6"])
    assert violations == []


def test_query_out_of_bounds_silent_skip() -> None:
    """Q 0 5 with N=3 → l<=r<N fail → parse skip."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3\n1 2 3\n1\nQ 0 5", expected_output="x"),
            SampleTestCase(input_text="3\n1 2 3\n1\nQ 0 2", expected_output="6"),
            SampleTestCase(input_text="3\n1 2 3\n1\nQ 0 2", expected_output="6"),
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
            SampleTestCase(input_text="3\n1 2 3\n1\nQ 0 2", expected_output="6"),
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
