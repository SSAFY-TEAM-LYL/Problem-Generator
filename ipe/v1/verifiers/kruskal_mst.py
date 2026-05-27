"""Kruskal MST symbolic verifier — D안 Phase 2c PR-D3.

variant: **Minimum Spanning Tree total weight** in undirected weighted graph
with non-negative integer weights. Output: 단일 정수 — MST 총 weight (또는
"-1" if disconnected).

Cross-algorithm golden: **Prim's algorithm O(V^2)** (Kruskal 과 다른 algorithm
— greedy + adjacency vs sort + DSU). 안전 상한 V <= 50.

narrative anchor: Union-Find (PR-C2) + Sort (PR-C5) 결합 algorithm — 기존
verifier 들의 sequel.

Invariants (4):
1. ``output_is_single_int``: 단일 정수 (또는 "-1" disconnected).
2. ``weight_non_negative``: connected 일 때 weight >= 0 (negative edge 금지).
3. ``connectivity_consistent``: graph connected ↔ output != -1.
4. ``weight_matches_prim_golden``: output == Prim's algorithm 결과.

Input format (1-indexed)::

    V E
    u_1 v_1 w_1
    ...
    u_E v_E w_E

(undirected, ``w_i >= 0``)

Output: 단일 정수 MST weight, 또는 ``-1`` (disconnected).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schema import (
    AlgorithmDesign,
    InvariantViolation,
    ProblemSpec,
    SolutionAttempt,
    TargetAlgorithm,
)

_BRUTE_V_LIMIT = 50
_INF = float("inf")


@dataclass(frozen=True)
class _Edge:
    u: int
    v: int
    w: int


@dataclass(frozen=True)
class _ParsedInput:
    v_count: int
    edges: tuple[_Edge, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 1:
        return None
    first = lines[0].split()
    if len(first) != 2:
        return None
    try:
        v_count, e_count = (int(x) for x in first)
    except ValueError:
        return None
    if v_count < 1 or v_count > _BRUTE_V_LIMIT or e_count < 0:
        return None
    if len(lines) - 1 != e_count:
        return None
    edges: list[_Edge] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) != 3:
            return None
        try:
            u_raw, v_raw, w_raw = (int(x) for x in parts)
        except ValueError:
            return None
        if not (1 <= u_raw <= v_count and 1 <= v_raw <= v_count):
            return None
        if w_raw < 0:
            return None
        edges.append(_Edge(u=u_raw - 1, v=v_raw - 1, w=w_raw))
    return _ParsedInput(v_count=v_count, edges=tuple(edges))


def _prim_mst(parsed: _ParsedInput) -> int | None:
    """Return MST total weight, or None if disconnected. O(V^2 + E)."""
    n = parsed.v_count
    if n == 0:
        return 0
    adj: dict[int, dict[int, int]] = {i: {} for i in range(n)}
    for e in parsed.edges:
        cur = adj[e.u].get(e.v)
        if cur is None or e.w < cur:
            adj[e.u][e.v] = e.w
            adj[e.v][e.u] = e.w
    in_mst = [False] * n
    min_edge: list[float] = [_INF] * n
    min_edge[0] = 0
    total = 0
    for _ in range(n):
        u = -1
        best: float = _INF
        for i in range(n):
            if not in_mst[i] and min_edge[i] < best:
                best = min_edge[i]
                u = i
        if u == -1 or best == _INF:
            return None
        in_mst[u] = True
        total += int(best)
        for v, w in adj[u].items():
            if not in_mst[v] and w < min_edge[v]:
                min_edge[v] = w
    return total


def _parse_output_int(output_str: str) -> int | None:
    s = output_str.strip()
    try:
        return int(s)
    except ValueError:
        return None


def _evidence(
    parsed: _ParsedInput, *, extra: dict[str, str] | None = None
) -> dict[str, str]:
    base = {"V": str(parsed.v_count), "E": str(len(parsed.edges))}
    if extra:
        base.update(extra)
    return base


class KruskalMSTVerifier:
    """Kruskal MST symbolic verifier (Prim cross-algorithm golden, V <= 50)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.KRUSKAL_MST

    def verify(
        self,
        spec: ProblemSpec,
        design: AlgorithmDesign,
        attempt: SolutionAttempt,
        sample_outputs: list[str],
    ) -> list[InvariantViolation]:
        del design, attempt
        violations: list[InvariantViolation] = []
        for i, (sample, output_str) in enumerate(
            zip(spec.sample_testcases, sample_outputs, strict=False)
        ):
            parsed = _parse_sample_input(sample.input_text)
            if parsed is None:
                continue
            sample_violation = self._check_sample(i, parsed, output_str)
            if sample_violation is not None:
                violations.append(sample_violation)
        return violations

    def _check_sample(
        self, i: int, parsed: _ParsedInput, output_str: str
    ) -> InvariantViolation | None:
        actual = _parse_output_int(output_str)
        if actual is None:
            return InvariantViolation(
                invariant_kind="output_is_single_int",
                description=f"sample {i}: output is not a single integer",
                evidence=_evidence(parsed, extra={"output": output_str[:60]}),
            )
        golden = _prim_mst(parsed)
        if golden is None:
            if actual != -1:
                return InvariantViolation(
                    invariant_kind="connectivity_consistent",
                    description=(
                        f"sample {i}: graph disconnected but output={actual} "
                        f"(-1 expected)"
                    ),
                    evidence=_evidence(parsed, extra={"actual": str(actual)}),
                )
            return None
        if actual == -1:
            return InvariantViolation(
                invariant_kind="connectivity_consistent",
                description=(
                    f"sample {i}: graph connected (Prim MST={golden}) but "
                    f"output=-1"
                ),
                evidence=_evidence(parsed, extra={"prim_golden": str(golden)}),
            )
        if actual < 0:
            return InvariantViolation(
                invariant_kind="weight_non_negative",
                description=f"sample {i}: output={actual} < 0",
                evidence=_evidence(parsed, extra={"actual": str(actual)}),
            )
        if actual != golden:
            return InvariantViolation(
                invariant_kind="weight_matches_prim_golden",
                description=(
                    f"sample {i}: output={actual} != prim_golden={golden}"
                ),
                evidence=_evidence(
                    parsed,
                    extra={"actual": str(actual), "prim_golden": str(golden)},
                ),
            )
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
