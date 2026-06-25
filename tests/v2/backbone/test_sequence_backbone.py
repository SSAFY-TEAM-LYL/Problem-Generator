"""SequenceBackbone unit tests (RFC backbone-generalization G1a).

Mirrors ``test_graph_backbone.py`` for the sequence family: the ``SequenceShape``
structural facts (narrative DATA + faithfulness check), ``resolve_backbone``
dispatch picking sequence over the ``NullBackbone`` fallback, and the
``owns`` realizability gate (int_array field with a *pinned* shape only).

``derive_edge_inputs`` is wired in G1b — here it is the empty tuple (the
graph-pre-5a shape), so these tests assert only the structural half.
"""

from __future__ import annotations

from ipe.v1.schema import ConstraintRange, IOFieldSpec, IOSchema, SequenceShape
from ipe.v2.backbone import (
    NullBackbone,
    SequenceBackbone,
    resolve_backbone,
)


def _io_schema(field: IOFieldSpec) -> IOSchema:
    return IOSchema(inputs=(field,), output_type="int", output_format="x")


def _int_array_field() -> IOFieldSpec:
    return IOFieldSpec(
        name="arr",
        type="int_array",
        size_range=ConstraintRange(name="arr", min_value=1, max_value=20),
        value_range=ConstraintRange(name="v", min_value=1, max_value=100),
    )


def _shaped_array(shape: SequenceShape) -> IOFieldSpec:
    return _int_array_field().model_copy(update={"sequence_shape": shape})


def _scalar_int_field() -> IOFieldSpec:
    return IOFieldSpec(name="k", type="int")


# ---------- structural_facts (sortedness / duplicates as machine statements) ----------


def test_structural_facts_emits_sortedness_and_duplicates() -> None:
    field = _shaped_array(
        SequenceShape(sortedness="non_decreasing", duplicates_allowed=True)
    )
    joined = " | ".join(SequenceBackbone().structural_facts(_io_schema(field)))
    assert "비내림차" in joined  # non_decreasing
    assert "중복" in joined  # duplicates fact present
    assert "arr" in joined  # 필드명 prefix


def test_structural_facts_unsorted_distinct() -> None:
    field = _shaped_array(
        SequenceShape(sortedness="unsorted", duplicates_allowed=False)
    )
    joined = " | ".join(SequenceBackbone().structural_facts(_io_schema(field)))
    assert "무정렬" in joined
    assert "없음" in joined or "서로" in joined  # distinct


def test_structural_facts_strictly_increasing_omits_redundant_duplicate_clause() -> None:
    # strictly_increasing implies distinct — no separate duplicates fact emitted.
    field = _shaped_array(SequenceShape(sortedness="strictly_increasing"))
    facts = SequenceBackbone().structural_facts(_io_schema(field))
    joined = " | ".join(facts)
    assert "순증가" in joined
    # exactly one fact (the sortedness statement); duplicates is implied, not restated
    assert len(facts) == 1


def test_structural_facts_empty_without_shape_or_non_sequence() -> None:
    # int_array but unpinned (legacy / byte-identical) → no facts
    assert SequenceBackbone().structural_facts(_io_schema(_int_array_field())) == []
    # non-sequence type → no facts
    assert SequenceBackbone().structural_facts(_io_schema(_scalar_int_field())) == []


# ---------- owns / resolve_backbone / NullBackbone dispatch ----------


def test_sequence_backbone_owns_only_pinned_array_schema() -> None:
    backbone = SequenceBackbone()
    assert (
        backbone.owns(_io_schema(_shaped_array(SequenceShape(sortedness="unsorted"))))
        is True
    )
    # unpinned int_array → not owned (falls through to Null = legacy path)
    assert backbone.owns(_io_schema(_int_array_field())) is False
    assert backbone.owns(_io_schema(_scalar_int_field())) is False


def test_resolve_backbone_routes_sequence_to_sequence_backbone() -> None:
    resolved = resolve_backbone(
        _io_schema(_shaped_array(SequenceShape(sortedness="non_decreasing")))
    )
    assert resolved.name == "sequence"
    assert isinstance(resolved, SequenceBackbone)


def test_resolve_backbone_falls_back_to_null_for_unpinned_array() -> None:
    resolved = resolve_backbone(_io_schema(_int_array_field()))
    assert resolved.name == "none"
    assert isinstance(resolved, NullBackbone)


def test_sequence_derive_edge_inputs_empty_until_g1b() -> None:
    # G1a ships the structural half only; edge-input derivation is wired in G1b.
    field = _shaped_array(SequenceShape(sortedness="unsorted"))
    assert SequenceBackbone().derive_edge_inputs(_io_schema(field)) == ()
