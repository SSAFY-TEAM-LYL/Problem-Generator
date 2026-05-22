"""AlgorithmDesign + 부속 모델 단위 테스트 (D안 PR-A1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    EdgeCase,
    Invariant,
)


def _valid_design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Dijkstra",
        complexity_target=ComplexityBound(
            time_big_o="O((V+E) log V)",
            space_big_o="O(V+E)",
        ),
        pseudocode="Initialize dist[s]=0; use priority queue; relax edges.",
        edge_cases=[
            EdgeCase(name="self_loop", description="u==v edge ignored"),
            EdgeCase(name="zero_weight", description="weight=0 edge allowed"),
        ],
        invariants=[
            Invariant(
                kind="non_negative_distance",
                description="모든 결과 거리 >= 0",
            ),
            Invariant(
                kind="triangle_inequality",
                description="d[v] <= d[u] + w(u,v) for every edge",
            ),
        ],
        data_structures=["priority_queue", "adjacency_list"],
    )


def test_algorithm_design_constructs_with_invariants() -> None:
    design = _valid_design()
    assert design.algorithm_name == "Dijkstra"
    assert len(design.invariants) == 2
    assert design.invariants[0].kind == "non_negative_distance"


def test_algorithm_design_is_frozen() -> None:
    design = _valid_design()
    with pytest.raises(ValidationError):
        design.algorithm_name = "BFS"


def test_algorithm_design_invariants_default_empty() -> None:
    design = AlgorithmDesign(
        algorithm_name="BFS",
        complexity_target=ComplexityBound(time_big_o="O(V+E)", space_big_o="O(V)"),
        pseudocode="queue-based traversal",
    )
    assert design.invariants == []
    assert design.edge_cases == []
    assert design.data_structures == []


def test_invariant_rejects_empty_kind() -> None:
    with pytest.raises(ValidationError):
        Invariant(kind="", description="x")


def test_invariant_formal_statement_is_optional() -> None:
    inv = Invariant(kind="k", description="d")
    assert inv.formal_statement is None
    inv2 = Invariant(
        kind="k",
        description="d",
        formal_statement="forall (u,v) in E: d[v] <= d[u] + w(u,v)",
    )
    assert inv2.formal_statement is not None


def test_complexity_bound_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        ComplexityBound(time_big_o="", space_big_o="O(V)")


def test_edge_case_example_input_is_optional() -> None:
    ec = EdgeCase(name="empty", description="V=0")
    assert ec.example_input is None
