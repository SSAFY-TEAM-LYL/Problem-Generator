"""결정론적 입력 생성 엔진 단위 테스트 (Phase 3 M4 step3 + step3b graph).

generate_inputs(contract, io_schema, seed): 결정론(같은 seed→같은 입력) + tier 범위
존중 + case 수 + int_array 구조 + edge boundary + graph 타입(weighted_edges 연결성/
tree_edges 트리 유효성/grid, disconnected bias).
"""

from __future__ import annotations

from ipe.v1.schema import (
    ConstraintRange,
    EdgeCaseSpec,
    GeneratorContract,
    IOFieldSpec,
    IOSchema,
    ScaleFamily,
)
from ipe.v2.generation.input_gen import generate_inputs, seed_from_run_id


def _io_schema(field: IOFieldSpec) -> IOSchema:
    return IOSchema(inputs=(field,), output_type="int", output_format="x")


def _int_array_field() -> IOFieldSpec:
    return IOFieldSpec(
        name="arr",
        type="int_array",
        size_range=ConstraintRange(name="arr", min_value=1, max_value=20),
        value_range=ConstraintRange(name="v", min_value=-5, max_value=5),
    )


# ---------- determinism ----------


def test_generate_inputs_is_deterministic_for_same_seed() -> None:
    schema = _io_schema(_int_array_field())
    contract = GeneratorContract(
        scale_families=(ScaleFamily(name="small", case_count=4),)
    )
    a = generate_inputs(contract, schema, seed=42)
    b = generate_inputs(contract, schema, seed=42)
    assert [c.input_text for c in a] == [c.input_text for c in b]


def test_generate_inputs_differs_for_different_seed() -> None:
    schema = _io_schema(_int_array_field())
    contract = GeneratorContract(
        scale_families=(ScaleFamily(name="small", case_count=5),)
    )
    a = generate_inputs(contract, schema, seed=1)
    b = generate_inputs(contract, schema, seed=2)
    assert [c.input_text for c in a] != [c.input_text for c in b]


# ---------- case counts ----------


def test_generate_inputs_case_count_and_categories() -> None:
    schema = _io_schema(_int_array_field())
    contract = GeneratorContract(
        scale_families=(
            ScaleFamily(name="small", case_count=3),
            ScaleFamily(name="large", case_count=2),
        ),
        edge_cases=(EdgeCaseSpec(name="single"), EdgeCaseSpec(name="empty")),
    )
    cases = generate_inputs(contract, schema, seed=0)
    assert len(cases) == 7  # 3 + 2 + 2 edge
    assert cases[0].category == "small"
    assert cases[-1].category == "empty"
    assert all(c.expected_output is None for c in cases)  # pending


# ---------- tier bounds ----------


def test_int_scalar_respects_tier_value_bounds() -> None:
    field = IOFieldSpec(
        name="N",
        type="int",
        value_range=ConstraintRange(name="N", min_value=1, max_value=1000000),
    )
    contract = GeneratorContract(
        scale_families=(
            ScaleFamily(
                name="small",
                case_count=10,
                field_bounds=(ConstraintRange(name="N", min_value=1, max_value=5),),
            ),
        )
    )
    for c in generate_inputs(contract, _io_schema(field), seed=7):
        assert 1 <= int(c.input_text) <= 5  # tier 가 값을 좁힘


def test_int_array_structure_and_element_bounds() -> None:
    schema = _io_schema(_int_array_field())
    contract = GeneratorContract(
        scale_families=(
            ScaleFamily(
                name="s",
                case_count=5,
                field_bounds=(ConstraintRange(name="arr", min_value=3, max_value=3),),
            ),
        )
    )
    for c in generate_inputs(contract, schema, seed=3):
        lines = c.input_text.split("\n")
        assert lines[0] == "3"  # N (tier 가 크기 고정)
        vals = lines[1].split()
        assert len(vals) == 3
        assert all(-5 <= int(v) <= 5 for v in vals)  # 원소 value_range


# ---------- edge boundary ----------


def test_edge_empty_array_yields_zero() -> None:
    schema = _io_schema(_int_array_field())
    contract = GeneratorContract(
        scale_families=(ScaleFamily(name="s", case_count=1),),
        edge_cases=(EdgeCaseSpec(name="empty"),),
    )
    empty = next(
        c for c in generate_inputs(contract, schema, seed=0) if c.category == "empty"
    )
    assert empty.input_text == "0"  # N=0


def test_edge_max_size_picks_upper_bound() -> None:
    field = IOFieldSpec(
        name="arr",
        type="int_array",
        size_range=ConstraintRange(name="arr", min_value=1, max_value=4),
        value_range=ConstraintRange(name="v", min_value=0, max_value=0),
    )
    contract = GeneratorContract(
        scale_families=(ScaleFamily(name="s", case_count=1),),
        edge_cases=(EdgeCaseSpec(name="max_size"),),
    )
    mx = next(
        c
        for c in generate_inputs(contract, _io_schema(field), seed=0)
        if c.category == "max_size"
    )
    assert mx.input_text.split("\n")[0] == "4"  # 크기 상한


# ---------- graph types (step3b) ----------


def _uf_components(n: int, edges: list[tuple[int, int]]) -> tuple[int, bool]:
    """union-find — (컴포넌트 수, 사이클 존재 여부). 정점 1..n."""
    parent = list(range(n + 1))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    has_cycle = False
    comps = n
    for u, v in edges:
        ru, rv = find(u), find(v)
        if ru == rv:
            has_cycle = True
        else:
            parent[ru] = rv
            comps -= 1
    return comps, has_cycle


def _weighted_edges_field(lo: int, hi: int) -> IOFieldSpec:
    return IOFieldSpec(
        name="edges",
        type="weighted_edges",
        size_range=ConstraintRange(name="edges", min_value=lo, max_value=hi),
        value_range=ConstraintRange(name="w", min_value=2, max_value=9),
    )


def _parse_graph(text: str) -> tuple[int, int, list[tuple[int, int, int]]]:
    lines = text.split("\n")
    v, e = (int(x) for x in lines[0].split())
    edges = [tuple(int(x) for x in ln.split()) for ln in lines[1:]]
    assert len(edges) == e
    return v, e, edges  # type: ignore[return-value]


def test_weighted_edges_connected_structure_and_bounds() -> None:
    schema = _io_schema(_weighted_edges_field(6, 6))  # V 고정
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=5),))
    for c in generate_inputs(contract, schema, seed=11):
        v, e, edges = _parse_graph(c.input_text)
        assert v == 6
        assert e >= v - 1  # 연결 backbone + extra
        for u, w_to, wt in edges:
            assert 1 <= u <= v and 1 <= w_to <= v  # 1-indexed
            assert u != w_to  # self-loop 없음
            assert 2 <= wt <= 9  # value_range = 가중치
        comps, _ = _uf_components(v, [(u, t) for u, t, _ in edges])
        assert comps == 1  # 연결 보장


def test_weighted_edges_deterministic_same_seed() -> None:
    schema = _io_schema(_weighted_edges_field(2, 12))
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=4),))
    a = generate_inputs(contract, schema, seed=5)
    b = generate_inputs(contract, schema, seed=5)
    assert [c.input_text for c in a] == [c.input_text for c in b]


def test_weighted_edges_tier_narrows_vertex_count() -> None:
    schema = _io_schema(_weighted_edges_field(1, 100))
    contract = GeneratorContract(
        scale_families=(
            ScaleFamily(
                name="s",
                case_count=3,
                field_bounds=(ConstraintRange(name="edges", min_value=3, max_value=3),),
            ),
        )
    )
    for c in generate_inputs(contract, schema, seed=2):
        v, _, _ = _parse_graph(c.input_text)
        assert v == 3


def test_weighted_edges_min_bias_is_tree_density() -> None:
    schema = _io_schema(_weighted_edges_field(4, 9))
    contract = GeneratorContract(
        scale_families=(ScaleFamily(name="s", case_count=1),),
        edge_cases=(EdgeCaseSpec(name="min_size"),),
    )
    mn = next(
        c for c in generate_inputs(contract, schema, seed=0) if c.category == "min_size"
    )
    v, e, _ = _parse_graph(mn.input_text)
    assert v == 4  # 크기 하한
    assert e == v - 1  # backbone 만 (최소 밀도)


def test_weighted_edges_empty_bias_single_vertex() -> None:
    schema = _io_schema(_weighted_edges_field(1, 9))
    contract = GeneratorContract(
        scale_families=(ScaleFamily(name="s", case_count=1),),
        edge_cases=(EdgeCaseSpec(name="empty"),),
    )
    empty = next(
        c for c in generate_inputs(contract, schema, seed=0) if c.category == "empty"
    )
    assert empty.input_text == "1 0"  # 단일 정점, 간선 0


def test_weighted_edges_disconnected_bias_two_components() -> None:
    schema = _io_schema(_weighted_edges_field(6, 6))
    contract = GeneratorContract(
        scale_families=(ScaleFamily(name="s", case_count=1),),
        edge_cases=(EdgeCaseSpec(name="disconnected"),),
    )
    dc = next(
        c
        for c in generate_inputs(contract, schema, seed=0)
        if c.category == "disconnected"
    )
    v, e, edges = _parse_graph(dc.input_text)
    assert v == 6
    assert e == v - 2  # 두 backbone: (A-1)+(B-1)
    comps, _ = _uf_components(v, [(u, t) for u, t, _ in edges])
    assert comps == 2  # 정확히 두 컴포넌트
    half = (v + 1) // 2
    for u, t, _ in edges:
        same_first = u <= half and t <= half
        same_second = u > half and t > half
        assert same_first or same_second  # 컴포넌트 간 간선 없음


def test_tree_edges_forms_valid_tree() -> None:
    field = IOFieldSpec(
        name="tree",
        type="tree_edges",
        size_range=ConstraintRange(name="tree", min_value=7, max_value=7),
    )
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=3),))
    for c in generate_inputs(contract, _io_schema(field), seed=9):
        lines = c.input_text.split("\n")
        v = int(lines[0])
        assert v == 7
        edges = [tuple(int(x) for x in ln.split()) for ln in lines[1:]]
        assert len(edges) == v - 1
        assert all(len(e) == 2 for e in edges)  # value_range 없음 → 무가중
        comps, has_cycle = _uf_components(v, edges)  # type: ignore[arg-type]
        assert comps == 1 and not has_cycle  # 유효한 트리


def test_tree_edges_with_value_range_adds_weights() -> None:
    field = IOFieldSpec(
        name="tree",
        type="tree_edges",
        size_range=ConstraintRange(name="tree", min_value=5, max_value=5),
        value_range=ConstraintRange(name="w", min_value=1, max_value=3),
    )
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=2),))
    for c in generate_inputs(contract, _io_schema(field), seed=4):
        lines = c.input_text.split("\n")
        for ln in lines[1:]:
            parts = ln.split()
            assert len(parts) == 3  # u v w
            assert 1 <= int(parts[2]) <= 3


def test_grid_matches_int_matrix_canonical() -> None:
    field = IOFieldSpec(
        name="board",
        type="grid",
        size_range=ConstraintRange(name="board", min_value=2, max_value=2),
        value_range=ConstraintRange(name="cell", min_value=0, max_value=1),
    )
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=2),))
    for c in generate_inputs(contract, _io_schema(field), seed=6):
        lines = c.input_text.split("\n")
        assert lines[0] == "2 2"  # R C (int_matrix 와 동일 규약)
        assert len(lines) == 3
        for row in lines[1:]:
            assert all(int(x) in (0, 1) for x in row.split())


# ---------- seed helper ----------


def test_seed_from_run_id_is_stable_and_distinct() -> None:
    assert seed_from_run_id("run-x") == seed_from_run_id("run-x")
    assert seed_from_run_id("run-x") != seed_from_run_id("run-y")
