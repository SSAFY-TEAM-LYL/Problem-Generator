"""DijkstraVerifier 단위 테스트 (D안 PR-A2).

각 invariant 의 통과/실패 fixture + parse-fail skip + register/get dispatch.
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
from ipe.v1.verifiers import DijkstraVerifier, get_verifier, register_verifier
from ipe.v1.verifiers.base import clear_registry


def _io() -> IOContract:
    return IOContract(
        input_format="V E s t followed by E lines of (u v w)",
        output_format="single integer or -1 if unreachable",
    )


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="Shortest path s->t",
        description="Find shortest path from s to t in weighted directed graph.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
            SampleTestCase(input_text="3 2 0 2\n0 1 1\n1 2 2", expected_output="3"),
            SampleTestCase(input_text="2 0 0 1", expected_output="-1"),
        ],
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Dijkstra",
        complexity_target=ComplexityBound(
            time_big_o="O((V+E) log V)", space_big_o="O(V+E)"
        ),
        pseudocode="Initialize dist[s]=0, priority queue, relax edges.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="def solve(): pass", iteration=0)


# ---------- Pass paths ----------


def test_passes_with_golden_outputs() -> None:
    v = DijkstraVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["5", "3", "-1"]
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert DijkstraVerifier.target_algorithm is TargetAlgorithm.DIJKSTRA
    assert DijkstraVerifier().target_algorithm is TargetAlgorithm.DIJKSTRA


# ---------- Invariant 1: non_negative ----------


def test_catches_negative_distance() -> None:
    v = DijkstraVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["-2", "3", "-1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "non_negative_distance"
    assert violations[0].evidence["actual_output"] == "-2"


# ---------- Invariant 2: source_zero ----------


def test_catches_source_equals_target_nonzero() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3 2 1 1\n0 1 5\n1 2 3", expected_output="0"),
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
        ],
    )
    v = DijkstraVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["5", "5", "5"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "source_zero"


# ---------- Invariant 3: reachability_consistent ----------


def test_catches_false_unreachable_claim() -> None:
    """첫 sample 은 명백히 reachable 인데 -1 출력 → reachability violation."""
    v = DijkstraVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["-1", "3", "-1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "reachability_consistent"


def test_catches_false_reachable_claim() -> None:
    """마지막 sample (V=2 edge=0) 은 unreachable 인데 5 출력 → reachability violation."""
    v = DijkstraVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["5", "3", "5"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "reachability_consistent"


# ---------- Invariant 4: shortest_distance_optimal ----------


def test_catches_suboptimal_distance() -> None:
    """3 vertex path: 0->1->2 cost 3. 100 은 suboptimal."""
    v = DijkstraVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["5", "100", "-1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "shortest_distance_optimal"
    assert violations[0].evidence["bellman_ford_golden"] == "3"
    assert violations[0].evidence["actual_output"] == "100"


def test_catches_shorter_than_optimal_distance() -> None:
    """LLM 이 거짓말 — 실제 정답보다 작은 거리 claim."""
    v = DijkstraVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["5", "1", "-1"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "shortest_distance_optimal"


# ---------- Parse skip ----------


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage non-numeric", expected_output="0"),
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
        ],
    )
    v = DijkstraVerifier()
    # 첫 sample 은 parse fail → skip. 두 번째는 actual=100 vs golden=5 → violation.
    # 세 번째는 actual=5 → pass.
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=["any", "100", "5"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "shortest_distance_optimal"


def test_unparseable_output_silent_skip() -> None:
    """output 이 정수 parse 실패하면 silent skip."""
    v = DijkstraVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["not-a-number", "3", "-1"],
    )
    assert violations == []


# ---------- Dispatch registry ----------


def test_get_verifier_returns_dijkstra_by_default() -> None:
    """ipe.v1.verifiers __init__ 이 import 시 DijkstraVerifier 자동 등록."""
    verifier = get_verifier(TargetAlgorithm.DIJKSTRA)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.DIJKSTRA


def test_register_verifier_round_trip() -> None:
    clear_registry()
    assert get_verifier(TargetAlgorithm.DIJKSTRA) is None
    instance = DijkstraVerifier()
    register_verifier(instance)
    assert get_verifier(TargetAlgorithm.DIJKSTRA) is instance
    # 다른 테스트 격리 회복
    clear_registry()
    register_verifier(DijkstraVerifier())


def test_count_engaged_samples_all_parseable() -> None:
    v = DijkstraVerifier()
    assert v.count_engaged_samples(_spec_three_samples()) == 3


def test_count_engaged_samples_some_unparseable() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage non-numeric", expected_output="0"),
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
            SampleTestCase(input_text="not a graph", expected_output="x"),
        ],
    )
    v = DijkstraVerifier()
    assert v.count_engaged_samples(spec) == 1


def test_count_engaged_samples_zero_when_all_unparseable() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="g1", expected_output="x"),
            SampleTestCase(input_text="g2", expected_output="x"),
            SampleTestCase(input_text="g3", expected_output="x"),
        ],
    )
    v = DijkstraVerifier()
    # verifier silent skip 전체 — H1 측정 시 v0 sample match 와 동일 효과 signal
    assert v.count_engaged_samples(spec) == 0


def test_register_verifier_replaces_existing() -> None:
    clear_registry()
    a = DijkstraVerifier()
    b = DijkstraVerifier()
    register_verifier(a)
    register_verifier(b)
    assert get_verifier(TargetAlgorithm.DIJKSTRA) is b
    # 다른 테스트 격리 회복
    clear_registry()
    register_verifier(DijkstraVerifier())
