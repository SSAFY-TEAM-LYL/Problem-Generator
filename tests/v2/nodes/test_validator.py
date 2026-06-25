"""IR validator 노드 단위 테스트 (Phase 2, RFC §6).

validate_ir(순수 Tier A) + make_validator_node(state.validation emit) +
route_after_validator(pass/routeback/end_validation 게이트).
"""

from __future__ import annotations

import pytest

from ipe.v1.schema import (
    ConstraintRange,
    IOFieldSpec,
    IOSchema,
    ProblemBlueprint,
    TargetAlgorithm,
)
from ipe.v2.nodes.validator import make_validator_node, validate_ir
from ipe.v2.router import route_after_validator
from ipe.v2.state import initial_v2_state


def _blueprint(
    *fields: IOFieldSpec,
    composition: tuple[TargetAlgorithm, ...] = (),
) -> ProblemBlueprint:
    return ProblemBlueprint(
        reduction_core=TargetAlgorithm.DIJKSTRA,
        composition=composition,
        domain="logistics",
        io_schema=IOSchema(
            inputs=fields, output_type="int", output_format="단일 정수"
        ),
    )


def _graph_field() -> IOFieldSpec:
    return IOFieldSpec(
        name="edges",
        type="weighted_edges",
        size_range=ConstraintRange(name="V", min_value=2, max_value=100),
        value_range=ConstraintRange(name="w", min_value=1, max_value=9),
    )


# ---------- validate_ir: Tier A ----------


def test_valid_graph_with_resolved_reference() -> None:
    bp = _blueprint(
        _graph_field(),
        IOFieldSpec(name="s", type="int", references="edges"),
    )
    report = validate_ir(bp, mode="p1")
    assert report.valid is True
    assert report.violations == ()


def test_collection_missing_size_range_is_violation() -> None:
    # weighted_edges 인데 size_range 없음 → 크기 미정
    bad = IOFieldSpec(name="edges", type="weighted_edges")
    report = validate_ir(_blueprint(bad), mode="p1")
    assert report.valid is False
    assert any("size_range" in v and "edges" in v for v in report.violations)


def test_dangling_reference_is_violation() -> None:
    bp = _blueprint(
        _graph_field(),
        IOFieldSpec(name="s", type="int", references="nonexistent"),
    )
    report = validate_ir(bp, mode="p1")
    assert report.valid is False
    assert any(
        "nonexistent" in v and "dangling" in v.lower() for v in report.violations
    )


def test_reference_to_scalar_is_violation() -> None:
    # 참조가 collection 이 아니라 다른 스칼라를 가리킴 → 크기 참조 불가
    bp = _blueprint(
        _graph_field(),
        IOFieldSpec(
            name="k",
            type="int",
            value_range=ConstraintRange(name="k", min_value=1, max_value=9),
        ),
        IOFieldSpec(name="s", type="int", references="k"),
    )
    report = validate_ir(bp, mode="p1")
    assert report.valid is False
    assert any("'s'" in v and "'k'" in v for v in report.violations)


def test_p2_empty_composition_is_violation() -> None:
    bp = _blueprint(_graph_field(), composition=())
    report = validate_ir(bp, mode="p2")
    assert report.valid is False
    assert any("composition" in v for v in report.violations)


def test_p1_empty_composition_is_ok() -> None:
    # P1 은 단일(합성 금지)이라 composition 빈값이 정상
    bp = _blueprint(_graph_field(), composition=())
    assert validate_ir(bp, mode="p1").valid is True


def test_p2_with_composition_is_valid() -> None:
    bp = _blueprint(_graph_field(), composition=(TargetAlgorithm.BINARY_SEARCH,))
    assert validate_ir(bp, mode="p2").valid is True


# ---------- make_validator_node ----------


def test_node_sets_validation_report() -> None:
    state = initial_v2_state("r", TargetAlgorithm.DIJKSTRA).model_copy(
        update={"blueprint": _blueprint(_graph_field())}
    )
    out = make_validator_node(mode="p1")(state)
    assert out.validation is not None
    assert out.validation.valid is True
    assert state.validation is None  # 원본 불변


def test_node_requires_blueprint() -> None:
    bare = initial_v2_state("r", TargetAlgorithm.DIJKSTRA)  # blueprint 없음
    with pytest.raises(ValueError, match="blueprint"):
        make_validator_node(mode="p1")(bare)


# ---------- route_after_validator ----------


def test_route_pass_when_valid() -> None:
    state = initial_v2_state("r", TargetAlgorithm.DIJKSTRA).model_copy(
        update={"validation": validate_ir(_blueprint(_graph_field()), mode="p1")}
    )
    assert route_after_validator(state) == "pass"


def test_route_routeback_when_invalid_with_budget() -> None:
    bad = validate_ir(
        _blueprint(IOFieldSpec(name="e", type="weighted_edges")), mode="p1"
    )
    state = initial_v2_state("r", TargetAlgorithm.DIJKSTRA).model_copy(
        update={
            "validation": bad,
            "validator_routebacks": 0,
            "max_validator_routebacks": 1,
        }
    )
    assert route_after_validator(state) == "routeback"


def test_route_end_when_invalid_budget_exhausted() -> None:
    bad = validate_ir(
        _blueprint(IOFieldSpec(name="e", type="weighted_edges")), mode="p1"
    )
    state = initial_v2_state("r", TargetAlgorithm.DIJKSTRA).model_copy(
        update={
            "validation": bad,
            "validator_routebacks": 1,
            "max_validator_routebacks": 1,
        }
    )
    assert route_after_validator(state) == "end_validation"


def test_route_end_when_report_absent() -> None:
    state = initial_v2_state("r", TargetAlgorithm.DIJKSTRA)  # validation=None
    assert route_after_validator(state) == "end_validation"
