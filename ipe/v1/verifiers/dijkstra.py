"""Dijkstra symbolic verifier — 4 invariants 결정론적 검증 (D안 PR-A2).

Invariants:
1. ``non_negative_distance``: 결과 거리 ≥ 0 또는 ``UNREACHABLE`` marker.
2. ``source_zero``: ``s == t`` 일 때 결과 = 0.
3. ``reachability_consistent``: BFS 로 검증한 도달가능성과 결과의 ``UNREACHABLE``
   여부 일치.
4. ``shortest_distance_optimal``: Bellman-Ford golden 과 결과 일치 (Dijkstra 와
   독립된 알고리즘으로 self-cross-check — non-negative weight 가정).

Input format (Phase 1 단순화):
    V E s t
    u_1 v_1 w_1
    ...
    u_E v_E w_E

Output format (Phase 1 단순화): 단일 정수 — d[s][t], unreachable 시 ``-1``.

format mismatch 면 verifier silent skip — PR-A4 의 executor 가 sample exact
match 로 fallback 처리. Phase 2 에서 IOContract 기반 generic parser 도입 예정.
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

UNREACHABLE = -1


@dataclass(frozen=True)
class _ParsedGraph:
    """parsed sample input → directed weighted graph."""

    V: int
    E: int
    s: int
    t: int
    edges: list[tuple[int, int, int]]


def _parse_sample_input(text: str) -> _ParsedGraph | None:
    """``V E s t`` + ``u v w`` E줄 형식 parse. 실패 시 None (verifier skip)."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None
    header = lines[0].split()
    if len(header) != 4:
        return None
    try:
        # V/E 는 graph theory convention (vertex/edge count) — domain naming 유지.
        V, E, s, t = (int(x) for x in header)  # noqa: N806
    except ValueError:
        return None
    if V <= 0 or E < 0:
        return None
    if not (0 <= s < V and 0 <= t < V):
        return None
    if len(lines) - 1 != E:
        return None
    edges: list[tuple[int, int, int]] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) != 3:
            return None
        try:
            u, v, w = (int(x) for x in parts)
        except ValueError:
            return None
        if not (0 <= u < V and 0 <= v < V):
            return None
        edges.append((u, v, w))
    return _ParsedGraph(V=V, E=E, s=s, t=t, edges=edges)


def _shortest_distance_bellman_ford(graph: _ParsedGraph) -> int:
    """Bellman-Ford 로 s→t shortest distance. unreachable 시 ``UNREACHABLE`` 반환.

    Dijkstra 와 독립된 알고리즘이라야 self-cross-check 의미. non-negative weight
    가정 시 두 알고리즘 결과 동일해야 함 — 불일치는 LLM 의 Dijkstra 구현 오류.
    """
    inf = float("inf")
    dist: list[float] = [inf] * graph.V
    dist[graph.s] = 0.0
    for _ in range(graph.V - 1):
        updated = False
        for u, v, w in graph.edges:
            if dist[u] != inf and dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                updated = True
        if not updated:
            break
    final = dist[graph.t]
    return UNREACHABLE if final == inf else int(final)


def _bfs_reachable_from_source(graph: _ParsedGraph) -> set[int]:
    """source 에서 도달 가능한 노드 집합 (directed edge follow)."""
    adj: dict[int, list[int]] = {i: [] for i in range(graph.V)}
    for u, v, _w in graph.edges:
        adj[u].append(v)
    visited: set[int] = {graph.s}
    stack: list[int] = [graph.s]
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in visited:
                visited.add(v)
                stack.append(v)
    return visited


def _evidence(
    graph: _ParsedGraph, actual: int, *, extra: dict[str, str] | None = None
) -> dict[str, str]:
    base = {
        "V": str(graph.V),
        "E": str(graph.E),
        "source": str(graph.s),
        "target": str(graph.t),
        "actual_output": str(actual),
    }
    if extra:
        base.update(extra)
    return base


class DijkstraVerifier:
    """Dijkstra-specific symbolic verifier.

    Each sample 마다 parse → 4 invariants 검증. 한 invariant 가 위반되면 그
    sample 은 더 이상 후속 invariant 검증 안 함 (short-circuit) — fix loop 의
    blocking signature 가 명확.
    """

    target_algorithm: TargetAlgorithm = TargetAlgorithm.DIJKSTRA

    def verify(
        self,
        spec: ProblemSpec,
        design: AlgorithmDesign,
        attempt: SolutionAttempt,
        sample_outputs: list[str],
    ) -> list[InvariantViolation]:
        # design/attempt 는 v0→v1 정보 이동의 anchor — 본 verifier 는 sample
        # input/output 만 사용. design.invariants 의 explicit 명세는 PR-A3 의
        # executor 가 feedback rendering 에 활용.
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
        # 1) non_negative
        if actual < 0 and actual != UNREACHABLE:
            return InvariantViolation(
                invariant_kind="non_negative_distance",
                description=f"sample {i}: actual={actual} < 0 (Dijkstra 거리는 음수 불가)",
                evidence=_evidence(graph, actual),
            )
        # 2) source_zero
        if graph.s == graph.t and actual != 0:
            return InvariantViolation(
                invariant_kind="source_zero",
                description=f"sample {i}: s==t={graph.s}, expected 0, got {actual}",
                evidence=_evidence(graph, actual),
            )
        # 3) reachability_consistent
        reachable = _bfs_reachable_from_source(graph)
        t_reachable = graph.t in reachable
        if actual == UNREACHABLE and t_reachable:
            desc = (
                f"sample {i}: actual=-1 (unreachable) but BFS shows "
                f"t={graph.t} reachable"
            )
            return InvariantViolation(
                invariant_kind="reachability_consistent",
                description=desc,
                evidence=_evidence(graph, actual),
            )
        if actual != UNREACHABLE and not t_reachable:
            desc = (
                f"sample {i}: actual={actual} (claims reachable) but BFS shows "
                f"t={graph.t} unreachable"
            )
            return InvariantViolation(
                invariant_kind="reachability_consistent",
                description=desc,
                evidence=_evidence(graph, actual),
            )
        # 4) shortest_distance_optimal (Bellman-Ford golden cross-check)
        golden = _shortest_distance_bellman_ford(graph)
        if actual != golden:
            return InvariantViolation(
                invariant_kind="shortest_distance_optimal",
                description=(
                    f"sample {i}: actual={actual} != Bellman-Ford golden={golden}"
                ),
                evidence=_evidence(
                    graph, actual, extra={"bellman_ford_golden": str(golden)}
                ),
            )
        return None
