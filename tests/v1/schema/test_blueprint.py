"""Blueprint-first 아티팩트 단위 테스트 (Phase 3 M3 step1).

ProblemBlueprint(frozen formal 계약) + Narrative(late) + NarrativeFaithfulnessReport
(round-trip). frozen + extra=forbid + 기본값 + 검증 규칙.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import (
    ConstraintRange,
    IOFieldSpec,
    IOSchema,
    Narrative,
    NarrativeFaithfulnessReport,
    OutputInvariant,
    ProblemBlueprint,
    TargetAlgorithm,
)


def _io_schema() -> IOSchema:
    return IOSchema(
        inputs=(
            IOFieldSpec(
                name="N",
                type="int",
                value_range=ConstraintRange(name="N", min_value=1, max_value=100000),
            ),
            IOFieldSpec(
                name="edges",
                type="weighted_edges",
                size_range=ConstraintRange(name="E", min_value=0, max_value=200000),
            ),
        ),
        output_type="int",
        output_format="단일 정수 (최단거리, 도달불가 시 -1)",
    )


def _blueprint() -> ProblemBlueprint:
    return ProblemBlueprint(
        reduction_core=TargetAlgorithm.DIJKSTRA,
        domain="logistics",
        io_schema=_io_schema(),
        output_invariants=(
            OutputInvariant(kind="non_negative", description="거리는 음수 불가"),
        ),
    )


# ---------- ProblemBlueprint ----------


def test_blueprint_minimal_construction_and_defaults() -> None:
    bp = _blueprint()
    assert bp.reduction_core is TargetAlgorithm.DIJKSTRA
    assert bp.composition == ()  # default
    assert bp.domain == "logistics"
    assert bp.io_schema.output_type == "int"
    assert len(bp.output_invariants) == 1


def test_blueprint_composition_records_synthesis_techniques() -> None:
    bp = ProblemBlueprint(
        reduction_core=TargetAlgorithm.DIJKSTRA,
        composition=(TargetAlgorithm.BINARY_SEARCH, TargetAlgorithm.UNION_FIND),
        domain="network",
        io_schema=_io_schema(),
    )
    assert bp.composition == (
        TargetAlgorithm.BINARY_SEARCH,
        TargetAlgorithm.UNION_FIND,
    )


def test_blueprint_is_frozen() -> None:
    bp = _blueprint()
    with pytest.raises(ValidationError):
        bp.domain = "other"  # type: ignore[misc]


def test_blueprint_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ProblemBlueprint(
            reduction_core=TargetAlgorithm.DIJKSTRA,
            domain="x",
            io_schema=_io_schema(),
            unexpected="nope",  # type: ignore[call-arg]
        )


def test_blueprint_requires_domain() -> None:
    with pytest.raises(ValidationError):
        ProblemBlueprint(
            reduction_core=TargetAlgorithm.DIJKSTRA,
            domain="",  # min_length=1
            io_schema=_io_schema(),
        )


# ---------- IOSchema / IOFieldSpec ----------


def test_io_schema_requires_at_least_one_input() -> None:
    with pytest.raises(ValidationError):
        IOSchema(inputs=(), output_type="int", output_format="x")


def test_io_field_optional_ranges_default_none() -> None:
    f = IOFieldSpec(name="s", type="string")
    assert f.size_range is None
    assert f.value_range is None
    assert f.description == ""


# ---------- Narrative ----------


def test_narrative_hidden_and_direct() -> None:
    hidden = Narrative(scenario="물류 센터 ...", hidden=True, domain="logistics")
    direct = Narrative(scenario="다익스트라를 구현하라", hidden=False, domain="algo")
    assert hidden.hidden is True
    assert direct.hidden is False


def test_narrative_requires_scenario() -> None:
    with pytest.raises(ValidationError):
        Narrative(scenario="", hidden=True, domain="d")


# ---------- NarrativeFaithfulnessReport ----------


def test_faithfulness_report_defaults_no_distortions() -> None:
    r = NarrativeFaithfulnessReport(faithful=True)
    assert r.faithful is True
    assert r.distortions == ()


def test_faithfulness_report_records_distortions() -> None:
    r = NarrativeFaithfulnessReport(
        faithful=False,
        distortions=("출력이 최댓값이라 기술됐으나 schema 는 최단거리",),
    )
    assert r.faithful is False
    assert len(r.distortions) == 1
