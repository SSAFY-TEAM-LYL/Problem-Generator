"""BFS (Breadth-First Search) symbolic verifier — D안 Phase 2a PR-B4.

variant: **Single-source, single-target shortest path** (unweighted, directed).
Phase 3 에서 all-targets variant 검토.

Invariants (4):
1. ``non_negative_distance``: 결과 거리 >= 0 또는 ``-1`` (unreachable).
2. ``source_zero``: s == t 일 때 결과 = 0.
3. ``reachability_consistent``: directed forward reachability 와 ``-1`` 여부
   일치.
4. ``distance_optimal``: Floyd-Warshall O(V³) golden (edge weight=1) 과 일치.

Input format (1-indexed, directed)::

    V E s t
    u_1 v_1
    ...
    u_E v_E

Output: 단일 정수 — s→t shortest edge count, unreachable 시 ``-1``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ..schema import (
    AlgorithmDesign,
    InvariantViolation,
    ProblemSpec,
    SolutionAttempt,
    TargetAlgorithm,
)

UNREACHABLE = -1


@dataclass(frozen=True)
class _ParsedGraph:
    v_count: int
    e_count: int
    s: int
    t: int
    edges: tuple[tuple[int, int], ...]


def _parse_sample_input(text: str) -> _ParsedGraph | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None
    header = lines[0].split()
    if len(header) != 4:
        return None
    try:
        v_count, e_count, s_raw, t_raw = (int(x) for x in header)
    except ValueError:
        return None
    if v_count <= 0 or e_count < 0:
        return None
    if not (1 <= s_raw <= v_count and 1 <= t_raw <= v_count):
        return None
    if len(lines) - 1 != e_count:
        return None
    edges: list[tuple[int, int]] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) != 2:
            return None
        try:
            u_raw, vv_raw = (int(x) for x in parts)
        except ValueError:
            return None
        if not (1 <= u_raw <= v_count and 1 <= vv_raw <= v_count):
            return None
        edges.append((u_raw - 1, vv_raw - 1))
    return _ParsedGraph(
        v_count=v_count,
        e_count=e_count,
        s=s_raw - 1,
        t=t_raw - 1,
        edges=tuple(edges),
    )


def _bfs_reachable_from_source(graph: _ParsedGraph) -> set[int]:
    adj: dict[int, list[int]] = {i: [] for i in range(graph.v_count)}
    for u, v in graph.edges:
        adj[u].append(v)
    visited: set[int] = {graph.s}
    queue: deque[int] = deque([graph.s])
    while queue:
        u = queue.popleft()
        for v in adj[u]:
            if v not in visited:
                visited.add(v)
                queue.append(v)
    return visited


def _floyd_warshall_unit(graph: _ParsedGraph) -> int:
    inf = float("inf")
    n = graph.v_count
    dist: list[list[float]] = [[inf] * n for _ in range(n)]
    for i in range(n):
        dist[i][i] = 0
    for u, v in graph.edges:
        if dist[u][v] > 1:
            dist[u][v] = 1
    for k in range(n):
        for i in range(n):
            for j in range(n):
                if dist[i][k] + dist[k][j] < dist[i][j]:
                    dist[i][j] = dist[i][k] + dist[k][j]
    final = dist[graph.s][graph.t]
    return UNREACHABLE if final == inf else int(final)


def _evidence(graph: _ParsedGraph, actual: int) -> dict[str, str]:
    return {
        "V": str(graph.v_count),
        "E": str(graph.e_count),
        "source": str(graph.s + 1),
        "target": str(graph.t + 1),
        "actual_output": str(actual),
    }


class BFSVerifier:
    """BFS (unweighted single-source single-target) specific symbolic verifier."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.BFS

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
            graph = _parse_sample_input(sample.input_text)
            if graph is None:
                continue
            try:
                actual = int(output_str.strip())
            except (ValueError, AttributeError):
                continue
            sample_violation = self._check_sample(i, graph, actual)
            if sample_violation is not None:
                violations.append(sample_violation)
        return violations

    def _check_sample(
        self, i: int, graph: _ParsedGraph, actual: int
    ) -> InvariantViolation | None:
        if actual < 0 and actual != UNREACHABLE:
            return InvariantViolation(
                invariant_kind="non_negative_distance",
                description=f"sample {i}: actual={actual} < 0 (BFS 거리 음수 불가)",
                evidence=_evidence(graph, actual),
            )
        if graph.s == graph.t and actual != 0:
            return InvariantViolation(
                invariant_kind="source_zero",
                description=(
                    f"sample {i}: s==t={graph.s + 1}, expected 0, got {actual}"
                ),
                evidence=_evidence(graph, actual),
            )
        reachable = _bfs_reachable_from_source(graph)
        t_reachable = graph.t in reachable
        if actual == UNREACHABLE and t_reachable:
            return InvariantViolation(
                invariant_kind="reachability_consistent",
                description=(
                    f"sample {i}: actual=-1 but BFS shows t={graph.t + 1} "
                    "reachable"
                ),
                evidence=_evidence(graph, actual),
            )
        if actual != UNREACHABLE and not t_reachable:
            return InvariantViolation(
                invariant_kind="reachability_consistent",
                description=(
                    f"sample {i}: actual={actual} but BFS shows t={graph.t + 1} "
                    "unreachable"
                ),
                evidence=_evidence(graph, actual),
            )
        golden = _floyd_warshall_unit(graph)
        if actual != golden:
            return InvariantViolation(
                invariant_kind="distance_optimal",
                description=(
                    f"sample {i}: actual={actual} != Floyd-Warshall golden="
                    f"{golden}"
                ),
                evidence={
                    **_evidence(graph, actual),
                    "floyd_warshall_golden": str(golden),
                },
            )
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
