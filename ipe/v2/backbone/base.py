"""Algorithm-backbone seam — the single interface behind which all algorithm-
family-specific structural modeling lives, so the universal pipeline skeleton
(modeling nodes, graph wiring, reconcile) never changes when a new backbone
(string / DP / geometry / …) is added. Today the sole concrete is
``GraphBackbone`` (``ipe/v2/backbone/graph.py``).

**Why this seam exists now (RFC graph-overfit, deliberately deferred).**
The single-IR RFC (``docs/improvements/2026-06-23_single-ir-architecture-rfc.md``)
is intentionally graph-specific — ``GraphShape`` is a field on ``IOFieldSpec`` and
the serializer hard-knows ``weighted_edges``/``tree_edges``. Generalizing the **IR
and serializer** is deferred to after all RFC phases land. This seam ensures the
*behavior that reads those graph fields* is already pluggable, so that later
generalization is a localized change inside backbone impls (+ one registry
append) rather than a skeleton rewrite.

**What IS behind the seam** (the skeleton reaches these ONLY via
``resolve_backbone`` — never by importing a graph-named function):

- ``structural_facts(io_schema)`` — IR → machine-derived structural statements
  (narrative DATA + faithfulness check). Was ``input_gen.render_structural_facts``.
- ``derive_edge_inputs(io_schema)`` — IR → realizable-degeneracy input set,
  *reserved* for RFC Phase 5: each ``DegenerateInput`` is fed into the reconcile
  differential set as Tier-B uniqueness evidence. The graph impl returns ``()``
  until Phase 5 (so today's pipeline stays byte-identical).

**What is NOT yet behind the seam** (documented deferred couplings — generalize
*after* the phases, tracked by the RFC's graph-overfit note). A future backbone
author must still touch these until the post-phase generalization:

- the serializer's graph branch (``input_gen._serialize_weighted_edges`` /
  ``_serialize_tree_edges`` / ``_backbone`` / ``_edge_key``) and the **format**
  prose (``input_gen._structural_clause`` / ``_vertex_index_phrase``) — format
  prose stays co-located with serialization because it must not drift from the
  emitted bytes (a different concern from the *semantic* facts above).
- the verifier dispatch (``ipe/v1/verifiers/*``) and the ``IOFieldType`` enum.
- reconcile's output-equivalence policy (exact ``==`` today; epsilon / custom
  checker is a future backbone axis, intentionally not built now).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ipe.v1.schema import IOSchema


@dataclass(frozen=True)
class DegenerateInput:
    """A realizable degenerate/edge input + its rationale, derived from the IR by a
    backbone. This is the *input* half of the RFC §3.3 ``ResolvedEdgeCase`` — the
    golden-filled ``expected_output`` is attached later (Phase 5).

    Consumed by the reconcile differential set as Tier-B uniqueness evidence:
    independent goldens agreeing on a degenerate input ⇒ that edge's semantics are
    uniquely determined (well-posed) and operationally defined by the agreed
    output; diverging ⇒ the IR is ill-posed *on that edge*, with this exact input
    as the witness.
    """

    name: str
    input_text: str
    rationale: str = ""


class AlgorithmBackbone(Protocol):
    """An algorithm-family backbone. See the module docstring for the seam
    contract and the list of couplings that are *not* yet behind it.

    Concretes are stateless singletons held in the ``resolve_backbone`` registry;
    a new family is added by implementing this Protocol and appending one entry —
    no skeleton (node / graph-wiring / reconcile) edit.
    """

    name: str

    def owns(self, io_schema: IOSchema) -> bool:
        """Does this backbone model this schema's structure? (registry dispatch key)"""
        ...

    def structural_facts(self, io_schema: IOSchema) -> list[str]:
        """IR → machine-derived structural statements (narrative DATA, faithfulness
        check). Empty list ⇒ no structural facts for this schema."""
        ...

    def derive_edge_inputs(self, io_schema: IOSchema) -> tuple[DegenerateInput, ...]:
        """IR → realizable-degeneracy inputs (RFC Phase 5 → reconcile differential
        set). Empty tuple ⇒ none derived (today's universal state)."""
        ...


class NullBackbone:
    """Fallback for schemas no concrete backbone owns — no structural facts, no
    degeneracies. Keeps ``resolve_backbone`` total (always returns a backbone) so
    callers never branch on ``None``."""

    name = "none"

    def owns(self, io_schema: IOSchema) -> bool:
        return False

    def structural_facts(self, io_schema: IOSchema) -> list[str]:
        return []

    def derive_edge_inputs(self, io_schema: IOSchema) -> tuple[DegenerateInput, ...]:
        return ()
