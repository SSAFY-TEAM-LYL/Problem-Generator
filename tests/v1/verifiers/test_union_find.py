"""UnionFindVerifier 단위 테스트 (D안 Phase 2b PR-C2)."""

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
from ipe.v1.verifiers import UnionFindVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N Q + Q ops (U x y | Q x y) 1-indexed",
        output_format="0 or 1 per Q op",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Union-Find",
        complexity_target=ComplexityBound(
            time_big_o="O(Q * alpha(N))", space_big_o="O(N)"
        ),
        pseudocode="parent[] init self; union by rank; path compression.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.UNION_FIND,
        title="Disjoint Set Union same-set query",
        description="DSU.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="4 4\nU 1 2\nU 3 4\nQ 1 2\nQ 1 3",
                expected_output="1\n0",
            ),
            SampleTestCase(
                input_text="3 3\nQ 1 1\nU 1 2\nQ 1 2",
                expected_output="1\n1",
            ),
            SampleTestCase(
                input_text="5 5\nU 1 2\nU 2 3\nU 4 5\nQ 1 3\nQ 1 4",
                expected_output="1\n0",
            ),
        ],
    )


def test_passes_with_golden_outputs() -> None:
    v = UnionFindVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1\n0", "1\n1", "1\n0"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert UnionFindVerifier.target_algorithm is TargetAlgorithm.UNION_FIND


def test_catches_output_count_mismatch() -> None:
    v = UnionFindVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1", "1\n1", "1\n0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_count_matches_queries"


def test_catches_non_binary_output() -> None:
    v = UnionFindVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1\n5", "1\n1", "1\n0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "binary_output_for_queries"


def test_catches_wrong_same_set() -> None:
    v = UnionFindVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["0\n0", "1\n1", "1\n0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "same_set_correctness"
    assert violations[0].evidence["naive_golden"] == "1"


def test_catches_false_same_set() -> None:
    v = UnionFindVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1\n1", "1\n1", "1\n0"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "same_set_correctness"


def test_transitive_union_correctness() -> None:
    v = UnionFindVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1\n0", "1\n1", "1\n0"],
    )
    assert violations == []


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.UNION_FIND,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3 1\nQ 1 2", expected_output="0"),
            SampleTestCase(input_text="3 1\nQ 1 2", expected_output="0"),
        ],
    )
    v = UnionFindVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "1", "0"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "same_set_correctness"


def test_invalid_op_kind_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.UNION_FIND,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1\nX 1 2", expected_output="x"),
            SampleTestCase(input_text="3 1\nQ 1 2", expected_output="0"),
            SampleTestCase(input_text="3 1\nQ 1 2", expected_output="0"),
        ],
    )
    v = UnionFindVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "0", "0"])
    assert violations == []


def test_count_engaged_all_parseable() -> None:
    assert UnionFindVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_count_engaged_partial() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.UNION_FIND,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3 1\nQ 1 2", expected_output="0"),
            SampleTestCase(input_text="bad N", expected_output="x"),
        ],
    )
    assert UnionFindVerifier().count_engaged_samples(spec) == 1


def test_get_verifier_returns_union_find_after_module_import() -> None:
    register_verifier(UnionFindVerifier())
    verifier = get_verifier(TargetAlgorithm.UNION_FIND)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.UNION_FIND
