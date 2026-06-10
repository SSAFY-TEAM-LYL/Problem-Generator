"""결정론적 입력 생성 엔진 단위 테스트 (Phase 3 M4 step3).

generate_inputs(contract, io_schema, seed): 결정론(같은 seed→같은 입력) + tier 범위
존중 + case 수 + int_array 구조 + edge boundary + 미지원 타입 raise.
"""

from __future__ import annotations

import pytest

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


# ---------- deferred types ----------


def test_unsupported_graph_type_raises() -> None:
    field = IOFieldSpec(
        name="edges",
        type="weighted_edges",
        size_range=ConstraintRange(name="E", min_value=1, max_value=5),
    )
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=1),))
    with pytest.raises(NotImplementedError, match="weighted_edges"):
        generate_inputs(contract, _io_schema(field), seed=0)


# ---------- seed helper ----------


def test_seed_from_run_id_is_stable_and_distinct() -> None:
    assert seed_from_run_id("run-x") == seed_from_run_id("run-x")
    assert seed_from_run_id("run-x") != seed_from_run_id("run-y")
