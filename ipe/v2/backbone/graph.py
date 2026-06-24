"""GraphBackbone — the sole concrete ``AlgorithmBackbone`` (graph-family structural
modeling). Owns the ``GraphShape``-reading *behavior*: the semantic structural
facts (narrative DATA / faithfulness check) and the Phase-5 edge-input derivation.

The ``GraphShape`` *type* still lives on ``IOFieldSpec`` (``ipe/v1/schema/blueprint``)
— generalizing the IR is deferred (see ``base.py``). So is the serializer's graph
branch and its **format** prose (``input_gen``): those stay with serialization to
avoid byte drift. This module owns only the *semantic* projection + degeneracy
derivation, which is what the skeleton consumes through the seam.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import DegenerateInput

if TYPE_CHECKING:
    from ipe.v1.schema import IOSchema

_GRAPH_TYPES = ("weighted_edges", "tree_edges")


class GraphBackbone:
    """Graph-family backbone. Owns a schema iff some graph field carries a pinned
    ``GraphShape`` (``None`` = legacy / byte-identical path with no facts to
    project, which falls through to ``NullBackbone``)."""

    name = "graph"

    def owns(self, io_schema: IOSchema) -> bool:
        return any(
            f.type in _GRAPH_TYPES and f.graph_shape is not None
            for f in io_schema.inputs
        )

    def structural_facts(self, io_schema: IOSchema) -> list[str]:
        """io_schema → graph **structural facts** as machine-derived statements
        (single source of truth, RFC F6~F8). Replaces the self-loop / multi-edge /
        directedness prose RULES that used to live in the formalizer & narrative
        prompts — narrative receives these as DATA to *describe*, and
        faithfulness/QA check narrative ↔ facts by **machine comparison**.

        Only graph fields with a pinned ``graph_shape`` contribute (``None`` ⇒
        skipped, so a non-graph or legacy schema yields ``[]``). Indexing (F9) is
        **format**, not semantics, so it is not emitted here — that is the format
        contract's job (``input_gen.render_input_format``).
        """
        facts: list[str] = []
        for f in io_schema.inputs:
            shape = f.graph_shape
            if f.type not in _GRAPH_TYPES or shape is None:
                continue
            prefix = f"{f.name}(그래프)"
            direction = "단방향(u→v)" if shape.directed else "양방향(u↔v, 무방향)"
            loop = "자기 간선(self-loop) 가능" if shape.self_loops else "자기 간선 없음"
            multi = (
                "같은 쌍 다중 간선 가능"
                if shape.multi_edges
                else "같은 쌍 다중 간선 없음(단순 그래프)"
            )
            conn = (
                "연결 보장"
                if shape.connectivity == "connected"
                else "연결 비보장(분리 컴포넌트·도달 불가 가능)"
            )
            facts.extend(
                [
                    f"{prefix}: {direction} 간선",
                    f"{prefix}: {loop}",
                    f"{prefix}: {multi}",
                    f"{prefix}: {conn}",
                ]
            )
        return facts

    def derive_edge_inputs(self, io_schema: IOSchema) -> tuple[DegenerateInput, ...]:
        """**Reserved for RFC Phase 5** (returns ``()`` today ⇒ byte-identical).

        Will enumerate the realizable-degeneracy set as a deterministic function of
        ``GraphShape`` + ``references`` + sizes, e.g.:

        - ``connectivity="maybe_disconnected"`` ⇒ an ``unreachable`` input;
        - a self-pointing scalar ``references`` ⇒ ``source_equals_target``;
        - any sized field ⇒ ``empty`` / ``min``.

        Each becomes a ``DegenerateInput`` added to the reconcile differential set
        (Tier-B uniqueness): goldens agreeing ⇒ that edge is well-posed and its
        output operationally defined; diverging ⇒ ill-posed IR with the witnessing
        input. A degeneracy the shape forbids (e.g. ``unreachable`` under
        ``connectivity="connected"``) is simply not in the realizable set, so it is
        never derived — which is why this derivation must be owned by the backbone
        that knows the shape, not the universal skeleton.
        """
        return ()
