"""GraphBackbone + algorithm-backbone seam unit tests.

Covers the behavior moved behind the seam (RFC graph-overfit deferral): structural
facts (was ``input_gen.render_structural_facts``), the ``resolve_backbone`` registry
dispatch, the ``NullBackbone`` fallback, and the Phase-5-reserved
``derive_edge_inputs``.
"""

from __future__ import annotations

from ipe.v1.schema import ConstraintRange, GraphShape, IOFieldSpec, IOSchema
from ipe.v2.backbone import (
    DegenerateInput,
    GraphBackbone,
    NullBackbone,
    resolve_backbone,
)


def _io_schema(field: IOFieldSpec) -> IOSchema:
    return IOSchema(inputs=(field,), output_type="int", output_format="x")


def _weighted_edges_field(lo: int = 2, hi: int = 10) -> IOFieldSpec:
    return IOFieldSpec(
        name="edges",
        type="weighted_edges",
        size_range=ConstraintRange(name="edges", min_value=lo, max_value=hi),
        value_range=ConstraintRange(name="w", min_value=2, max_value=9),
    )


def _shaped_edges(shape: GraphShape) -> IOFieldSpec:
    return _weighted_edges_field().model_copy(update={"graph_shape": shape})


def _int_array_field() -> IOFieldSpec:
    return IOFieldSpec(
        name="arr",
        type="int_array",
        size_range=ConstraintRange(name="arr", min_value=1, max_value=20),
    )


# ---------- structural_facts (moved verbatim from render_structural_facts) ----------


def test_structural_facts_emits_pinned_graph_facts() -> None:
    field = _shaped_edges(
        GraphShape(
            directed=False,
            self_loops=False,
            multi_edges=True,
            connectivity="connected",
        )
    )
    joined = " | ".join(GraphBackbone().structural_facts(_io_schema(field)))
    assert "양방향" in joined  # directed=False
    assert "자기 간선 없음" in joined
    assert "다중 간선 가능" in joined
    assert "연결 보장" in joined
    assert "edges" in joined  # 필드명 prefix


def test_structural_facts_directed_self_loop_multi() -> None:
    field = _shaped_edges(
        GraphShape(
            directed=True,
            self_loops=True,
            multi_edges=False,
            connectivity="maybe_disconnected",
        )
    )
    joined = " | ".join(GraphBackbone().structural_facts(_io_schema(field)))
    assert "단방향" in joined
    assert "자기 간선(self-loop) 가능" in joined
    assert "단순 그래프" in joined  # multi_edges=False
    assert "도달 불가 가능" in joined  # maybe_disconnected


def test_structural_facts_empty_without_shape_or_non_graph() -> None:
    # graph 타입이지만 shape 미핀(레거시) → 빈 list (byte-identical 경로)
    assert GraphBackbone().structural_facts(_io_schema(_weighted_edges_field())) == []
    # 비-graph 타입 → 빈 list
    assert GraphBackbone().structural_facts(_io_schema(_int_array_field())) == []


# ---------- owns / resolve_backbone / NullBackbone dispatch (the seam itself) ----------


def test_graph_backbone_owns_only_pinned_graph_schema() -> None:
    backbone = GraphBackbone()
    assert backbone.owns(_io_schema(_shaped_edges(GraphShape(directed=True)))) is True
    # shape 미핀 graph → 소유 안 함 (NullBackbone 으로 fall-through = 레거시 무사실 경로)
    assert backbone.owns(_io_schema(_weighted_edges_field())) is False
    assert backbone.owns(_io_schema(_int_array_field())) is False


def test_resolve_backbone_routes_graph_to_graph_backbone() -> None:
    resolved = resolve_backbone(_io_schema(_shaped_edges(GraphShape(directed=True))))
    assert resolved.name == "graph"
    assert isinstance(resolved, GraphBackbone)


def test_resolve_backbone_falls_back_to_null_for_non_graph() -> None:
    schema = _io_schema(_int_array_field())
    resolved = resolve_backbone(schema)
    assert resolved.name == "none"
    assert isinstance(resolved, NullBackbone)
    # NullBackbone 은 구조사실/엣지입력 둘 다 비어 있음 (skeleton 이 None 분기 불필요)
    assert resolved.structural_facts(schema) == []
    assert resolved.derive_edge_inputs(schema) == ()


def test_resolve_backbone_falls_back_to_null_for_unpinned_graph() -> None:
    # graph 타입이라도 shape 미핀이면 어떤 backbone 도 소유 안 함 → Null (레거시 경로)
    resolved = resolve_backbone(_io_schema(_weighted_edges_field()))
    assert resolved.name == "none"


# ---------- derive_edge_inputs: Phase 5a 활성 (realizable 퇴화 입력) ----------


def test_graph_derive_edge_inputs_min_and_unreachable_for_separable() -> None:
    # maybe_disconnected weighted_edges → min(경계) + unreachable(분리) 둘 다 실현가능
    field = _shaped_edges(
        GraphShape(directed=False, connectivity="maybe_disconnected")
    )
    edges = GraphBackbone().derive_edge_inputs(_io_schema(field))
    names = [e.name for e in edges]
    assert names == ["min", "unreachable"]
    assert all(isinstance(e, DegenerateInput) for e in edges)
    assert all(e.input_text for e in edges)  # 비지 않은 직렬화 입력
    assert all(e.rationale for e in edges)  # 사람 설명 존재


def test_graph_derive_edge_inputs_min_only_for_connected() -> None:
    # connectivity=connected → 분리 불가 → unreachable 미실현, min 만
    field = _shaped_edges(GraphShape(directed=True, connectivity="connected"))
    edges = GraphBackbone().derive_edge_inputs(_io_schema(field))
    assert [e.name for e in edges] == ["min"]


def test_graph_derive_edge_inputs_deterministic() -> None:
    # 고정 seed — 같은 io_schema 면 항상 같은 입력 (reconcile diff == edge_filler fill 보장)
    field = _shaped_edges(
        GraphShape(directed=False, connectivity="maybe_disconnected")
    )
    schema = _io_schema(field)
    first = GraphBackbone().derive_edge_inputs(schema)
    second = GraphBackbone().derive_edge_inputs(schema)
    assert first == second


def test_degenerate_input_is_constructible() -> None:
    # Phase 5 가 채울 타입 — frozen dataclass 계약(name/input_text/rationale) 확인.
    di = DegenerateInput(
        name="unreachable", input_text="2 0\n", rationale="분리 컴포넌트"
    )
    assert di.name == "unreachable"
    assert di.input_text == "2 0\n"
    assert di.rationale == "분리 컴포넌트"
