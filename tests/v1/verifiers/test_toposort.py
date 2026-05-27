"""TopologicalSortVerifier 단위 테스트 (D안 Phase 2b PR-C3)."""

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
from ipe.v1.verifiers import (
    TopologicalSortVerifier,
    get_verifier,
    register_verifier,
)


def _io() -> IOContract:
    return IOContract(
        input_format="N M + M edges (u v) 1-indexed",
        output_format="N integers — permutation of 1..N",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Topological Sort",
        complexity_target=ComplexityBound(time_big_o="O(V+E)", space_big_o="O(V+E)"),
        pseudocode="Kahn or DFS post-order reversed.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.TOPOSORT,
        title="Topological Sort",
        description="DAG ordering.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="4 3\n1 2\n2 3\n3 4",
                expected_output="1 2 3 4",
            ),
            SampleTestCase(
                input_text="3 2\n1 3\n2 3",
                expected_output="1 2 3",
            ),
            SampleTestCase(
                input_text="5 4\n1 2\n1 3\n2 4\n3 5",
                expected_output="1 2 3 4 5",
            ),
        ],
    )


def test_passes_with_valid_order() -> None:
    v = TopologicalSortVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 2 3 4", "2 1 3", "1 3 2 5 4"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert TopologicalSortVerifier.target_algorithm is TargetAlgorithm.TOPOSORT


def test_catches_output_length_mismatch() -> None:
    v = TopologicalSortVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 2 3", "1 2 3", "1 2 3 4 5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_length_matches_n"


def test_catches_non_permutation_duplicate() -> None:
    v = TopologicalSortVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 2 2 4", "1 2 3", "1 2 3 4 5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_permutation"


def test_catches_non_permutation_out_of_range() -> None:
    v = TopologicalSortVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 2 3 5", "1 2 3", "1 2 3 4 5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_permutation"


def test_catches_edge_order_violation() -> None:
    v = TopologicalSortVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["2 1 3 4", "1 2 3", "1 2 3 4 5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "edges_respect_order"
    assert "1->2" in violations[0].description


def test_accepts_multiple_valid_orders() -> None:
    v = TopologicalSortVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TOPOSORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1\n1 2", expected_output="1 2 3"),
            SampleTestCase(input_text="3 1\n1 2", expected_output="1 3 2"),
            SampleTestCase(input_text="3 1\n1 2", expected_output="3 1 2"),
        ],
    )
    violations = v.verify(
        spec,
        _design(),
        _attempt(),
        sample_outputs=["1 2 3", "1 3 2", "3 1 2"],
    )
    assert violations == []


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TOPOSORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2 1\n1 2", expected_output="1 2"),
            SampleTestCase(input_text="2 1\n1 2", expected_output="1 2"),
        ],
    )
    v = TopologicalSortVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["x", "1 2", "1 2"])
    assert violations == []


def test_cycle_input_silent_skip() -> None:
    """Cycle 있으면 verifier engagement 0 (Kahn fail)."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TOPOSORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 3\n1 2\n2 3\n3 1", expected_output="?"),
            SampleTestCase(input_text="2 1\n1 2", expected_output="1 2"),
            SampleTestCase(input_text="2 1\n1 2", expected_output="1 2"),
        ],
    )
    v = TopologicalSortVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["?", "1 2", "1 2"])
    assert violations == []
    assert v.count_engaged_samples(spec) == 2


def test_self_loop_input_silent_skip() -> None:
    """u == v self-loop 은 invalid DAG → parse fail → skip."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TOPOSORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 1\n1 1", expected_output="x"),
            SampleTestCase(input_text="2 1\n1 2", expected_output="1 2"),
            SampleTestCase(input_text="2 1\n1 2", expected_output="1 2"),
        ],
    )
    v = TopologicalSortVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert TopologicalSortVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_count_engaged_partial() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TOPOSORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3 2\n1 2\n2 3", expected_output="1 2 3"),
            SampleTestCase(input_text="3 3\n1 2\n2 3\n3 1", expected_output="x"),
        ],
    )
    assert TopologicalSortVerifier().count_engaged_samples(spec) == 1


def test_get_verifier_returns_toposort_after_module_import() -> None:
    register_verifier(TopologicalSortVerifier())
    verifier = get_verifier(TargetAlgorithm.TOPOSORT)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.TOPOSORT


def test_whitespace_tolerant_multiline_output() -> None:
    """Output 이 newline 으로 구분되어도 split() 으로 처리."""
    v = TopologicalSortVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TOPOSORT,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 1\n1 2", expected_output="1\n2\n3"),
            SampleTestCase(input_text="3 1\n1 2", expected_output="1\n2\n3"),
            SampleTestCase(input_text="3 1\n1 2", expected_output="1\n2\n3"),
        ],
    )
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=["1\n2\n3", "3\n1\n2", "1 2 3"]
    )
    assert violations == []
