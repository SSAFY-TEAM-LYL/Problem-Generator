"""KruskalMSTVerifier 단위 테스트 (D안 Phase 2c PR-D3)."""

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
from ipe.v1.verifiers import KruskalMSTVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="V E + E undirected edges (u v w), w >= 0",
        output_format="single int — MST weight, or -1 if disconnected",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Kruskal MST",
        complexity_target=ComplexityBound(time_big_o="O(E log E)", space_big_o="O(V)"),
        pseudocode="Sort edges + Union-Find merge.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.KRUSKAL_MST,
        title="Kruskal MST",
        description="MST weight",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="4 5\n1 2 1\n2 3 2\n3 4 3\n1 4 10\n2 4 5",
                expected_output="6",
            ),
            SampleTestCase(
                input_text="3 2\n1 2 5\n2 3 7",
                expected_output="12",
            ),
            SampleTestCase(
                input_text="4 2\n1 2 1\n3 4 2",
                expected_output="-1",
            ),
        ],
    )


def test_passes_with_correct_mst() -> None:
    v = KruskalMSTVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["6", "12", "-1"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert KruskalMSTVerifier.target_algorithm is TargetAlgorithm.KRUSKAL_MST


def test_catches_non_integer_output() -> None:
    v = KruskalMSTVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["six", "12", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_single_int"


def test_catches_wrong_disconnected_should_be_minus_one() -> None:
    v = KruskalMSTVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["6", "12", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "connectivity_consistent"


def test_catches_wrong_minus_one_when_connected() -> None:
    v = KruskalMSTVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["-1", "12", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "connectivity_consistent"


def test_catches_suboptimal_mst_weight() -> None:
    v = KruskalMSTVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["7", "12", "-1"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "weight_matches_prim_golden"
    assert violations[0].evidence["prim_golden"] == "6"


def test_single_node_no_edges_returns_zero() -> None:
    v = KruskalMSTVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KRUSKAL_MST,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="1 0", expected_output="0"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["0", "5", "5"])
    assert violations == []


def test_parallel_edges_minimum_selected() -> None:
    v = KruskalMSTVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KRUSKAL_MST,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="2 3\n1 2 5\n1 2 3\n1 2 7",
                expected_output="3",
            ),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["3", "5", "5"])
    assert violations == []


def test_negative_weight_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KRUSKAL_MST,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 1\n1 2 -5", expected_output="x"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
        ],
    )
    v = KruskalMSTVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KRUSKAL_MST,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
        ],
    )
    v = KruskalMSTVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_v_too_large_silent_skip() -> None:
    v_count = 55
    edges_text = "\n".join(f"{i + 1} {i + 2} 1" for i in range(v_count - 1))
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KRUSKAL_MST,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text=f"{v_count} {v_count - 1}\n{edges_text}",
                expected_output="x",
            ),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
        ],
    )
    v = KruskalMSTVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert KruskalMSTVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_get_verifier_returns_kruskal_mst_after_module_import() -> None:
    register_verifier(KruskalMSTVerifier())
    verifier = get_verifier(TargetAlgorithm.KRUSKAL_MST)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.KRUSKAL_MST


def test_classic_cycle_excludes_heaviest_edge() -> None:
    """Triangle (1,2,1) (2,3,2) (1,3,100). MST = 1+2 = 3."""
    v = KruskalMSTVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KRUSKAL_MST,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="3 3\n1 2 1\n2 3 2\n1 3 100",
                expected_output="3",
            ),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
            SampleTestCase(input_text="2 1\n1 2 5", expected_output="5"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["3", "5", "5"])
    assert violations == []
