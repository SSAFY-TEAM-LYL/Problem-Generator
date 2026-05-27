"""Bellman-Ford symbolic verifier — D안 Phase 2c PR-D1.

variant: **classic single-source single-target shortest path with negative
weights allowed (no negative cycles)**. Output: 단일 정수 — d[s][t] (없으면
-1).

Dijkstra (PR-A) 와 동일 format 이지만 **negative edge 허용** — narrative
"Dijkstra ↔ Bellman-Ford cross-check" 의 base.

Golden: **Floyd-Warshall O(V^3)** 으로 cross-check (different algorithm,
verifier 독립 anchor). 안전 상한 V <= 30.

Invariants (4):
1. ``output_is_single_int``: 단일 정수 (또는 "-1" unreachable).
2. ``source_target_self_zero``: s == t 일 때 d = 0.
3. ``no_negative_cycle_in_input``: input 에 reachable negative cycle 없음
   (cycle 있으면 spec invalid → silent skip).
4. ``distance_matches_floyd_warshall``: output == Floyd-Warshall golden.

Input format (1-indexed)::

    V E s t
    u_1 v_1 w_1
    ...
    u_E v_E w_E

(w 는 음수 허용)

Output: 단일 정수 d[s][t], 또는 "-1" (unreachable).
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

_BRUTE_V_LIMIT = 30
_INF = float("inf")


@dataclass(frozen=True)
class _Edge:
    u: int
    v: int
    w: int


@dataclass(frozen=True)
class _ParsedInput:
    v_count: int
    s: int
    t: int
    edges: tuple[_Edge, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 1:
        return None
    first = lines[0].split()
    if len(first) != 4:
        return None
    try:
        v_count, e_count, s_raw, t_raw = (int(x) for x in first)
    except ValueError:
        return None
    if v_count < 1 or v_count > _BRUTE_V_LIMIT or e_count < 0:
        return None
    if not (1 <= s_raw <= v_count and 1 <= t_raw <= v_count):
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
        edges.append(_Edge(u=u_raw - 1, v=v_raw - 1, w=w_raw))
    return _ParsedInput(
        v_count=v_count, s=s_raw - 1, t=t_raw - 1, edges=tuple(edges)
    )


def _floyd_warshall(parsed: _ParsedInput) -> list[list[float]]:
    n = parsed.v_count
    dist: list[list[float]] = [[_INF] * n for _ in range(n)]
    for i in range(n):
        dist[i][i] = 0
    for e in parsed.edges:
        if e.w < dist[e.u][e.v]:
            dist[e.u][e.v] = e.w
    for k in range(n):
        for i in range(n):
            for j in range(n):
                via = dist[i][k] + dist[k][j]
                if via < dist[i][j]:
                    dist[i][j] = via
    return dist


def _has_reachable_negative_cycle(parsed: _ParsedInput) -> bool:
    n = parsed.v_count
    s = parsed.s
    dist: list[float] = [_INF] * n
    dist[s] = 0
    for _ in range(n - 1):
        updated = False
        for e in parsed.edges:
            if dist[e.u] != _INF and dist[e.u] + e.w < dist[e.v]:
                dist[e.v] = dist[e.u] + e.w
                updated = True
        if not updated:
            break
    return any(
        dist[e.u] != _INF and dist[e.u] + e.w < dist[e.v] for e in parsed.edges
    )


def _parse_output_int(output_str: str) -> int | None:
    s = output_str.strip()
    try:
        return int(s)
    except ValueError:
        return None


def _evidence(
    parsed: _ParsedInput, *, extra: dict[str, str] | None = None
) -> dict[str, str]:
    base = {
        "V": str(parsed.v_count),
        "E": str(len(parsed.edges)),
        "s": str(parsed.s + 1),
        "t": str(parsed.t + 1),
    }
    if extra:
        base.update(extra)
    return base


class BellmanFordVerifier:
    """Bellman-Ford symbolic verifier (Floyd-Warshall golden, V <= 30)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.BELLMAN_FORD

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
            if _has_reachable_negative_cycle(parsed):
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
        if parsed.s == parsed.t and actual != 0:
            return InvariantViolation(
                invariant_kind="source_target_self_zero",
                description=f"sample {i}: s == t but output={actual}",
                evidence=_evidence(parsed, extra={"actual": str(actual)}),
            )
        dist = _floyd_warshall(parsed)
        expected_f = dist[parsed.s][parsed.t]
        if expected_f == _INF:
            if actual != -1:
                return InvariantViolation(
                    invariant_kind="distance_matches_floyd_warshall",
                    description=(
                        f"sample {i}: actual={actual} but Floyd-Warshall "
                        f"says unreachable (-1 expected)"
                    ),
                    evidence=_evidence(parsed, extra={"actual": str(actual)}),
                )
        else:
            expected = int(expected_f)
            if actual != expected:
                return InvariantViolation(
                    invariant_kind="distance_matches_floyd_warshall",
                    description=(
                        f"sample {i}: actual={actual} != "
                        f"floyd_warshall_golden={expected}"
                    ),
                    evidence=_evidence(
                        parsed,
                        extra={
                            "actual": str(actual),
                            "floyd_golden": str(expected),
                        },
                    ),
                )
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        engaged = 0
        for sample in spec.sample_testcases:
            parsed = _parse_sample_input(sample.input_text)
            if parsed is None:
                continue
            if _has_reachable_negative_cycle(parsed):
                continue
            engaged += 1
        return engaged
