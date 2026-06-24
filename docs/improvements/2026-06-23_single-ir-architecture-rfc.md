# RFC: Single Canonical IR + Pure Projections + Two Verified Creative Slots

**Status:** Draft for review · **Scope:** `ipe/v2/` generation pipeline + `ipe/v1/schema` data model
**Author role:** architecture · **Date:** 2026-06-23

## 0. Thesis

The pipeline's correctness problem is not in any node — every node is locally correct and the QA gate is correctly rejecting. The problem is **topological**: the same problem-fact is independently re-expressed by ~8 artifacts, and their mutual consistency is held together by accumulated prompt RULES rather than by construction. The contradiction surface is O(N²) in the number of independently-authored representations. The recent "freeze-by-code" patches (which lifted P1 from 11% to 67%) are each an instance of one principle — *project the fact from a single source instead of re-authoring it* — applied reactively, one fact at a time.

This RFC makes that principle the explicit architecture: **one rich frozen `ProblemIR`; every correctness artifact a pure function of it; exactly two LLM slots that EXPRESS the problem (narrative prose, golden code), each verified against the IR.** Operating invariant: *every fact has exactly one authored source; if a fact appears in two independently-authored artifacts, that is a latent contradiction by definition.*

The codebase is already ~60% of the way there. This RFC names the remaining gaps precisely and sequences the rest.

---

## 1. Fact inventory

For a representative graph problem the canonical fact bundle is: *"directed/undirected graph, V vertices indexed 1..V, no self-loops, multi-edges allowed, connectivity not guaranteed, weights w∈[lo,hi]; s,t are query vertices in [1,V]; output is the shortest s→t distance, −1 if unreachable, 0 if s==t; ties don't change the answer."* Here is where each sub-fact is authored and re-stated today.

| # | Fact | Authored at (single intended source) | Re-stated / consumed at | Status |
|---|------|--------------------------------------|--------------------------|--------|
| F1 | field name + type | `make_formalizer_node` → `IOSchema.inputs` (`ipe/v1/schema/blueprint.py:42`) | every consumer below | single source ✓ |
| F2 | collection size range | formalizer → `IOFieldSpec.size_range` | `render_constraints`, `render_input_format`, `render_input_parser`, `generate_inputs`, sample-gen | **projected ✓** (Phase 0) |
| F3 | element/weight value range | formalizer → `IOFieldSpec.value_range` | same as F2 | **projected ✓** |
| F4 | scalar pointer (s,t → graph) | formalizer → `IOFieldSpec.references` | `_serialize_reference`, `render_constraints` (`1≤s≤V`), `_render_field` | **projected ✓** (the template) |
| F5 | fixed columns (K attrs/row) | formalizer → `IOFieldSpec.cols_range` | `_serialize_int_matrix`, `render_constraints`, `_render_field` | **projected ✓** |
| F6 | **self-loop policy** | *nowhere as data* — hardcoded in `_serialize_weighted_edges`/`_backbone` (`ipe/v2/generation/input_gen.py`) | prose rule in formalizer prompt, narrative prompt, `_FORMAT_TEXT`, parser docstring | **redundant prose ✗** |
| F7 | **multi-edge / connectivity policy** | *nowhere as data* — hardcoded biases in `_serialize_weighted_edges`, `_backbone`, `_serialize_tree_edges` | same prose sites as F6 | **redundant prose ✗** |
| F8 | **directedness** | *undecided anywhere* — serializer emits `u v w`; `DijkstraVerifier._bfs_reachable_from_source` assumes directed (`ipe/v1/verifiers/dijkstra.py:104`); golden chooses freely; narrative may say "two-way roads" arbitrarily | latent | **missing ✗ (latent contradiction)** |
| F9 | **1-indexing** | *nowhere as data* — hardcoded in `_backbone` and `_serialize_reference` | prose in formalizer/narrative, `_FORMAT_TEXT`, parser | **redundant prose ✗** |
| F10 | output type + format | formalizer → `IOSchema.output_type/output_format` | `io_contract.output_format` carry-over (spec_bridge), narrative told NOT to restate | single source ✓ |
| F11 | **edge-case semantics** (s==t→0, unreachable→−1, multi-edge/0-budget handling) | formalizer → `output_invariants` as **prose** (`OutputInvariant.kind/description`) | narrative must echo, QA ambiguity reviewer checks, golden implements operationally | **redundant prose ✗** (4-way) |
| F12 | **answer uniqueness / tie-break** | formalizer → prose `output_invariants` | narrative echoes, QA ambiguity checks, reconcile enforces operationally | **redundant prose ✗** |
| F13 | constraints table | `render_constraints(io_schema)` (`ipe/v2/generation/input_gen.py`) | spec_bridge injects, QA reads | **projected ✓** |
| F14 | input_format prose | `render_input_format(io_schema)` | spec_bridge → `io_contract.input_format`, golden/brute coder | **projected ✓** |
| F15 | stdin parser preamble | `render_input_parser(io_schema)` (`ipe/v2/generation/input_parser.py`) | injected to golden/brute via `parse_discipline` (`ipe/v1/nodes/coder.py`) | **projected ✓** |
| F16 | sample inputs | `_generate_sample_inputs` (`ipe/v2/nodes/spec_bridge.py`); expected by `make_sample_filler_node` (golden) | — | **projected ✓** |
| F17 | **scale tiers** (field_bounds) | `make_generator_designer_node` LLM → `ScaleFamily.field_bounds` | `generate_inputs`; must mirror io_schema names+ranges (prompt rule) | **redundant LLM ✗** |
| F18 | **edge cases to generate** | generator_designer LLM → `EdgeCaseSpec.name`; collapsed to 5 biases by `_edge_bias` | `generate_inputs`; prompt forbids unrealizable names | **redundant LLM ✗** (pure risk — see §4) |
| F19 | target algorithm + composition + domain | strategist → `StrategySeed`; carried structurally into blueprint and spec | verifier dispatch, Tier-B switch (`ipe/v2/graph.py`), narrative | single source ✓ |
| F20 | description | `narrative.scenario`; carried into spec | QA reads | single source ✓ |
| F21 | title (+ time/mem limits) | **spec_bridge LLM** — the only surviving authored output | spec | **vestigial LLM ✗** |

**Reading of the inventory.** Phase-0 patches already collapsed F2–F5, F13–F16 to projections. The remaining redundancy is three clusters:

- **Structural facts F6–F9** live *only* as code constants inside the `input_gen.py` serializer and are re-stated as prose rules in three prompts. They are not fields anywhere. F8 (directedness) is not even decided — a genuine latent contradiction.
- **Output semantics F11–F12** are authored as prose by formalizer, must be echoed by narrative, checked by QA, and implemented by golden — a 4-way surface held together entirely by prompt rules.
- **Generator contract F17–F18** is LLM-authored but adds no information the IR doesn't already determine; F18 adds only *risk* (the LLM can name an edge kind the serializer cannot produce, which survives as a category and contradicts the format → QA reject). F21 (title) is a full Opus call producing one line.

---

## 2. Single-source assignment table

Target state: each fact has exactly one authored home in the enriched IR (or is a strategist seed absorbed into it); every consumer is a pure function.

| Fact | Canonical home (enriched IR) | Projected to (pure code, cannot contradict) |
|------|------------------------------|---------------------------------------------|
| F1–F5 | `IOFieldSpec` (unchanged) | constraints, format, parser, generator, samples |
| F6 self-loops | **`GraphShape.self_loops: bool`** (new) | serializers read it; `render_structural_facts` (new) emits it as machine fact; narrative receives as DATA; faithfulness + validator check it |
| F7 multi-edge + connectivity | **`GraphShape.multi_edges: bool`, `GraphShape.connectivity`** (new) | same consumers as F6 |
| F8 directedness | **`GraphShape.directed: bool`** (new) | serializer comment, format prose, narrative DATA, golden contract, verifier |
| F9 indexing | **`IOSchema.indexing: Literal[0,1]=1`** (new) | `_backbone`, `_serialize_reference`, constraints, format, parser |
| F10 output type/format | `IOSchema` (unchanged) | io_contract carry-over |
| F11 edge-case semantics | **`ResolvedEdgeCase[]`** (new): inputs derived from IR realizable-degeneracy set; **outputs golden-filled** | narrative DESCRIBES observed; QA checks narrative↔resolved; validator checks coverage |
| F12 answer uniqueness | **`IOSchema.answer_uniqueness: Literal["tie_invariant","tie_broken","unverified"]`** (new) + reconcile proof | validator; narrative |
| F13–F16 | already projected from `IOSchema` | unchanged |
| F17 scale tiers | **derived** from `size_range`/`value_range` (deterministic policy) | `generate_inputs` |
| F18 edge cases | **derived** from realizable-degeneracy set (function of `GraphShape`/types) | `generate_inputs` |
| F19 algo/composition/domain | `ProblemBlueprint` (strategist seed, carried) | verifier, Tier-B switch, narrative |
| F20 description | `narrative.scenario` | spec |
| F21 title | **fold into `NarrativeDraft.title`** (creative slot 1) or derive | spec |

After this assignment, **the only artifacts a human/LLM authors are: the strategist seed (F19), the IOSchema+GraphShape (F1–F10, formalizer), the narrative prose (F20–F21), and the golden code (F11 outputs).** Everything else is `f(IR)`.

---

## 3. Enriched `ProblemIR` schema

Concrete additions to `ipe/v1/schema/blueprint.py`. All keep `frozen=True, extra="forbid"`.

### 3.1 `GraphShape` — lift the implicit serializer constants (F6–F9)

```python
class GraphShape(BaseModel):
    """Structural facts for graph-typed fields. Today these are HARD-CODED in
    input_gen._serialize_weighted_edges/_backbone and only RE-STATED as prose
    rules in formalizer/narrative prompts. Making them IR fields means the
    serializer READS them (one truth) and narrative/QA/faithfulness check
    against them by machine instead of by prompt rule."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    directed: bool                                  # F8: today UNDECIDED — must be pinned
    self_loops: bool = False                        # F6: serializer constant today
    multi_edges: bool = True                         # F7: weighted_edges constant today
    connectivity: Literal["connected", "maybe_disconnected"] = "maybe_disconnected"
```

`IOFieldSpec` gains `graph_shape: GraphShape | None = None` (required by validator when `type in {weighted_edges, tree_edges}`; for `tree_edges` the validator forces `connectivity="connected", multi_edges=False, self_loops=False` — the tree invariant becomes a *checked* fact, not a prose promise).

**Behavior preservation:** the field defaults equal today's serializer constants, so Phase 1 is a no-op on generated bytes until formalizer starts varying them. The win is that `_serialize_weighted_edges` reads `field.graph_shape.*` instead of hardcoding, and a new pure projection emits the structural facts for narrative/QA to consume:

```python
def render_structural_facts(io_schema: IOSchema) -> list[str]:
    """IR → machine-derived structural statements (one source). Replaces the
    self-loop/multi-edge/indexing prose RULES in formalizer & narrative prompts."""
```

### 3.2 `IOSchema` — indexing + uniqueness (F9, F12)

```python
class IOSchema(BaseModel):
    ...
    indexing: Literal[0, 1] = 1                      # F9: hardcoded in _backbone today
    answer_uniqueness: Literal[                      # F12: today prose in output_invariants
        "tie_invariant",   # output value identical for all optimal solutions (preferred)
        "tie_broken",      # tie-break rule fully specified by the IR
        "unverified",      # validator must reject for P2
    ] = "unverified"
```

### 3.3 Edge-case semantics → golden-defined (F11)

Replace the prose `output_invariants(kind="edge_case_semantics")` pattern with a *machine* representation whose **inputs are derived from the IR** and whose **outputs are filled by the verified golden** — exactly mirroring how `sample_filler` already bootstraps sample expected outputs (`ipe/v2/nodes/sample_filler.py`).

```python
class ResolvedEdgeCase(BaseModel):
    """A realizable degenerate input + its golden-defined output.
    input_text is DERIVED deterministically from the IR's realizable-degeneracy
    set (function of types + GraphShape); expected_output is filled post-reconcile
    by running the canonical golden (operational definition). rationale is the
    human description that narrative must match and QA checks against."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str                          # "source_equals_target" | "unreachable" | "empty" | ...
    input_text: str
    expected_output: str | None = None # golden-filled (None = pending), like GeneratedTestCase
    rationale: str = ""
```

**How edge semantics become golden-defined instead of prose-formalized.** The realizable-degeneracy set is *derivable*: a graph with `connectivity="maybe_disconnected"` admits an `unreachable` case; `references` self-pointing admits `source_equals_target`; any sized field admits `empty`/`min`. A new pure function `derive_edge_inputs(io_schema)` enumerates these inputs (it already exists in spirit as `_edge_bias` + the `bias` machinery in `input_gen.py`). Crucially, **these edge inputs are added to the reconcile differential set** (today `reconcile` only diffs sample inputs — `ipe/v1/nodes/reconciler.py`). Then:

- golden×K agreement on an edge input ⇒ that edge's semantics are **uniquely determined** (well-posed) AND **operationally defined** by the agreed output. Disagreement ⇒ the IR is ill-posed *on that edge* → reject early with a pointer to the exact input (the P2 lever, §6).
- the agreed output is stored as `ResolvedEdgeCase.expected_output`.
- narrative DESCRIBES the observed `rationale`; faithfulness/QA check description ↔ resolved pairs by machine.

This removes formalizer's prose edge-case authoring entirely. The IR declares *which* edges exist (derived); the golden defines *what they do* (verified unique by reconcile); the prose merely describes.

### 3.4 `ProblemBlueprint`

No new top-level fields beyond the nested ones above. `output_invariants` is retained only for *symbolic* invariants consumed by `ipe/v1/verifiers/*` (e.g. `non_negative`, `triangle_inequality`); the `edge_case_semantics`/`answer_uniqueness` *kinds* migrate out to §3.2/§3.3 where they are machine-usable.

---

## 4. Node → role mapping

Three roles only: **IR authors** (write the single source), **verified creative slots** (express the problem, checked against the IR), **pure projections** (f(IR), no LLM), plus **validators** (check a relationship).

| Node (file) | Today | Target role | Change |
|-------------|-------|-------------|--------|
| `strategist` | LLM seed | **seed author** (creative, upstream) | unchanged — emits `StrategySeed` (F19), absorbed into IR by formalizer |
| `formalizer` | LLM | **THE IR author** (critical single source) | enrich output schema (GraphShape/indexing/uniqueness); **drop** the structural prose RULES (§3.1) since they become checked fields |
| `narrative` | LLM | **verified creative slot 1** | unchanged role; receives structural + resolved-edge facts as DATA to describe, not rules to avoid |
| `faithfulness` | LLM | **verifier: narrative ↔ IR** | augment with machine checks against `GraphShape`/`ResolvedEdgeCase` |
| `golden_i` / `brute` | LLM | **verified creative slot 2** | unchanged; reconcile differential set extended to edge inputs (§3.3) |
| `reconciler` | code | **verifier: golden ↔ IR + uniqueness** | diff over sample **+ derived edge** inputs |
| `spec_bridge` | LLM (Opus) | **PURE PROJECTION** | **drop the LLM call.** Today it authors only `title`; everything else is already carried/projected. Split into `spec_projection` (parser/constraints/io_contract/samples — pure `f(IR)`) + late attach of `description`/`title` |
| `generator_designer` | LLM (Opus) | **PURE PROJECTION** | **drop the LLM call.** `field_bounds` (F17) derive from `size/value_range` by deterministic tier policy; `edge_cases` (F18) derive from the realizable set. The LLM's only freedom is collapsed to 5 biases by `_edge_bias` anyway |
| `input_generator`, `sample_filler`, `suite_assembler` | code | **pure projections** | unchanged (already LLM-free) |
| **`validator`** (NEW) | — | **verifier: IR ↔ itself (well-definedness)** | new node after formalizer (§6) |
| `qa_*` reviewers | LLM (Sonnet) | **independent audit** (final) | unchanged role; ambiguity reviewer's edge/tie checks become partially redundant with validator (defense in depth) |

**Net:** LLM calls in the *correctness path* drop from 6 (strategist, formalizer, narrative, spec_bridge, generator_designer, golden×K/brute) to the **two creative slots + formalizer (IR author) + strategist (seed)**. spec_bridge and generator_designer — two full Opus calls per run — become free code. The contradiction surface collapses to exactly two edges: **narrative ↔ IR** (faithfulness) and **golden ↔ IR** (reconcile/executor). Every projection is `f(IR)` and therefore cannot disagree with the IR or with another projection.

---

## 5. Migration plan (incremental, each shippable + measurable)

Measurement protocol matches the existing one (`project_ship_rate_analysis`): fixed batch, N≥18 per mode, P1/P2 ship-rate before/after, plus per-failure-class counts from `V2FinalStatus`.

**Phase 0 — DONE (reframed).** The freeze patches (`render_constraints`/`render_input_format`/`render_input_parser`/`_generate_sample_inputs`, `references`, `cols_range`, self-loop prose alignment) each lifted one fact (F2–F5, F13–F16) from redundant authoring to projection. Result: P1 11%→67%. Those were the first applications of the §0 invariant; Phases 1–5 finish it.

**Phase 1 — Structural IR fields (F6–F9).** Add `GraphShape` + `IOSchema.indexing`; make `input_gen.py` serializers READ them (defaults = current constants ⇒ byte-identical output, zero regression risk); have formalizer EMIT them (structured) and DROP the structural prose rules; add `render_structural_facts` projection feeding narrative/QA. *Leverage:* eliminates the self-loop/multi-edge/**directedness** contradiction class (F8 is currently un-pinned). *Measure:* `fail_qa` ambiguity/format-contradiction count; P1/P2 ship-rate.

**Phase 2 — IR validator, pure-code tier (P2 lever, §6).** New `validator` node after formalizer: completeness + realizability + coverage checks, all pure code, plus `composition` non-empty for P2 and `answer_uniqueness != "unverified"` for P2. Add an **ill-posed back-route** to the strategist/formalizer (mirror the existing QA back-route topology, `ipe/v2/router.py`, `graph.py:_wire_qa`). *Leverage:* highest for P2 — rejects orphan-field/empty-composition/unrealizable-edge/uncovered-degeneracy IRs *before* spending golden×K + brute + suite + 4 reviewers, and makes the rejection *repairable*. *Measure:* P2 cost-per-ship; fraction of P2 failures caught pre-synthesis.

**Phase 3 — `generator_designer` → projection (F17–F18).** Replace the LLM with `derive_scale_families(io_schema)` (log-spaced tiers within declared ranges) + `derive_edge_cases(io_schema)` (one `EdgeCaseSpec` per realizable bias). Delete the prompt section fighting unrealizable kinds. *Leverage:* removes the F18 reject class entirely and one Opus call. Depends on Phase 1. *Measure:* unrealizable-category `fail_qa` count (expect →0); cost/run.

**Phase 4 — `spec_bridge` → projection (F21).** Split into pure `spec_projection` + fold `title` into `NarrativeDraft`. Delete the Opus call and its structured-output failure mode (`fail_spec_authoring`). *Leverage:* removes a full Opus call and an entire failure class. *Measure:* cost/run; `fail_spec_authoring` →0.

**Phase 5 — Golden-defined edge semantics (F11) + reorder.** Add `ResolvedEdgeCase` derivation; extend reconcile differential to edge inputs; add an edge-filler node (clone `sample_filler`); move narrative to *describe observed* behavior (after synthesis — consistent with the existing `narrative_revise` back-route). *Leverage:* deepest; fully realizes "golden operationally defines semantics, prose describes." Largest reorder, so last. *Measure:* edge-semantics `fail_qa` count; faithfulness false-reject rate.

Ordering rationale: Phase 1 unblocks 2 and 3 (the realizable set needs `GraphShape`); Phase 2 is the highest-leverage P2 fix and only needs Phase 1; Phases 3–4 are pure simplification; Phase 5 is the deepest and is sequenced last because it requires reordering the DAG.

---

## 6. IR validator + early well-definedness (the P2 lever)

P2 ships 0% because the *composition is often ill-posed* (the rules don't uniquely determine the answer), and **no downstream gate can repair an ill-posed problem**. Today the only thing that detects non-uniqueness is `reconcile` (golden×K diverge → `fail_synthesis_rejected`) — but that fires *after* full synthesis, reports as "synthesis rejected" (not "ill-posed IR"), and has **no back-route**: the run just dies. The validator turns this into a cheap, diagnostic, repairable front gate.

**Tier A — pure-code structural checks (free, always on, before synthesis):**

- **Completeness:** every collection field has a `size_range`; every `references` resolves to an existing collection; `output_type` consistent with `output_format`.
- **Orphan-field detection** (today a formalizer prose rule): any comparison/threshold scalar must have a per-element data field it compares against; otherwise the problem is unsolvable from its inputs → reject.
- **Realizability** (today a `generator_designer` prose rule): the realizable-degeneracy set is derivable; any declared edge category outside `{empty, min, max, disconnected, source_equals_target}` is rejected at the IR, not discovered as a QA category mismatch.
- **Coverage:** every *realizable* degeneracy (e.g. `connectivity="maybe_disconnected"` ⇒ `unreachable` exists) must have a `ResolvedEdgeCase` slot, so semantics can't be silently undefined.
- **P2 well-formedness:** `composition` non-empty and `answer_uniqueness != "unverified"`.

**Tier B — uniqueness, the part pure code can't decide:**

1. **Operational (preferred, reuses the moat):** include the derived edge inputs in the reconcile differential set (§3.3). Independent goldens agreeing ⇒ unique; diverging ⇒ ill-posed, with the *exact* witnessing input. This needs the goldens to run, but the back-route makes it repairable.
2. **Cheap pre-synthesis probe (optional, P2 only):** a single Haiku/Sonnet "well-posedness auditor" that reads the **IR** (not the narrative) and answers "does this io_schema + output definition + invariants determine a single answer for every input in range? list ambiguities." This is the faithfulness pattern turned inward (IR ↔ itself: *is this a total, single-valued function spec?*). One cheap call vs. burning the whole expensive tail.

**Back-route.** On validator reject (or Tier-B divergence), route to strategist/formalizer with the witnessing diagnostic, bounded by a budget exactly like `max_qa_routebacks` / `max_iterations` (`ipe/v2/state.py`, `router.py:route_after_qa`). This is the missing repair path: an ill-posed P2 composition gets one or two attempts to re-pick the composition before failing, instead of dying on the first reconcile divergence.

The three gates now map cleanly onto the three relationships: **validator** = IR ↔ itself (well-defined function), **faithfulness** = narrative ↔ IR, **reconcile/executor** = golden ↔ IR. The validator is the cheap front gate that's currently missing.

---

## 7. Risks and trade-offs

- **The IR author becomes the single point of failure (by design).** Today consistency is smeared across prompts so no single node failure is fatal; concentrating truth in formalizer means a formalizer error propagates to *every* projection. Mitigation: that is exactly what the **validator** (§6) guards — a rich IR is *checkable*, a smeared one is not. We trade many weak prompt-rule guards for one strong machine guard. Net safer, but the formalizer prompt + IR schema become the highest-value review surface.

- **Schema/serializer churn touches the hot path.** `IOFieldSpec`/`IOSchema` are imported by 14 types in `V2State` and consumed by every projection + the v1 verifiers. Mitigation: all new fields are optional with defaults equal to today's constants (Phase 1 is byte-identical until formalizer varies them); round-trip tests already guard serializer↔parser drift and must be extended to the new fields.

- **Some "creativity" is genuinely lost — and that's correct here.** Collapsing `generator_designer` removes an LLM's choice of test strategy. But that choice is already collapsed to 5 biases by `_edge_bias`; the LLM contributed no realizable information, only the risk of unrealizable categories. If per-algorithm stress strategy later proves to add real signal, it can return as a *projection input* (a small typed policy table keyed by `reduction_core`), not a free-text LLM artifact.

- **Edge semantics that resist derivation.** Some output semantics aren't reducible to a small realizable set (e.g. complex multi-condition tie-breaks). For those, F11/F12 stay partly prose in `output_invariants`, and the golden-defined `ResolvedEdgeCase` covers only the enumerable degeneracies. This is a graceful boundary, not a cliff: the validator still forces `answer_uniqueness != "unverified"` for P2, pushing authors toward tie-invariant outputs.

- **Phase 5 reorder risk.** Moving narrative after synthesis is the one change that alters control flow materially (recursion budgets in `config.py`, the back-route wiring in `_wire_qa`). It is sequenced last and is independently revertible; Phases 1–4 deliver most of the contradiction collapse without it.

- **What could regress.** (a) If new `GraphShape` defaults are set wrong, every graph problem's generated bytes shift at once — mitigated by default-equals-constant + round-trip tests. (b) A too-strict validator could over-reject well-posed-but-unusual IRs — mitigated by measuring validator reject reasons against the fixed batch before enabling the back-route as a hard gate. (c) Folding `title` into narrative couples two concerns in one creative slot — acceptable since title is cosmetic.

---

## Key files this RFC touches

- Data model (enrich): `ipe/v1/schema/blueprint.py`, `ipe/v1/schema/problem_spec.py`, `ipe/v1/schema/test_suite.py`
- Projections (read new fields; absorb dropped LLM nodes): `ipe/v2/generation/input_gen.py`, `ipe/v2/generation/input_parser.py`
- Nodes → projections: `ipe/v2/nodes/spec_bridge.py`, `ipe/v2/nodes/generator_designer.py`
- IR authors / creative slots (prompt changes): `ipe/v2/nodes/formalizer.py`, `ipe/v2/nodes/narrative.py`, `ipe/v2/nodes/faithfulness.py`
- Verification (extend differential to edge inputs): `ipe/v1/nodes/reconciler.py`, `ipe/v2/nodes/sample_filler.py`
- New validator + wiring + back-route: `ipe/v2/graph.py`, `ipe/v2/router.py`, `ipe/v2/state.py`

## Immediate bug flagged (independent of full refactor)

**F8 (directedness) is unspecified anywhere** — the serializer emits `u v w`, `DijkstraVerifier._bfs_reachable_from_source` (`ipe/v1/verifiers/dijkstra.py:104`) assumes directed, and the narrative can describe edges as bidirectional with nothing to catch the mismatch. Pinning `GraphShape.directed` (Phase 1) closes a contradiction that no current prompt rule even mentions.
