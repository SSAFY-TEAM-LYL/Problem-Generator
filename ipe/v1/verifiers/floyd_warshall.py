"""Floyd-Warshall symbolic verifier — D안 Phase 2c PR-D2.

variant: **all-pairs shortest path** in directed graph with non-negative or
negative weights (no negative cycle). Output: V × V distance matrix.

Cross-algorithm golden: **V times Bellman-Ford single-source** (O(V^2 * E)),
verifier 와 다른 algorithm 으로 cross-check. 안전 상한 V <= 25.

Invariants (4):
1. ``output_is_v_by_v_matrix``: V lines, each V integer tokens.
2. ``diagonal_is_zero``: ``d[i][i] == 0`` 모든 i.
3. ``triangle_inequality``: 모든 (i,j,k) 에 대해
   ``d[i][j] <= d[i][k] + d[k][j]`` (모두 finite 일 때).
4. ``matches_bellman_ford_golden``: output[i][j] == V-times Bellman-Ford 결과.

Input format (1-indexed)::

    V E
    u_1 v_1 w_1
    ...
    u_E v_E w_E

(w 음수 허용, reachable negative cycle 금지)

Output: V lines, each V tokens. ``d[i][j]`` 또는 ``-1`` (unreachable).
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

_BRUTE_V_LIMIT = 25
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
        edges.append(_Edge(u=u_raw - 1, v=v_raw - 1, w=w_raw))
    return _ParsedInput(v_count=v_count, edges=tuple(edges))


def _bellman_ford_single_source(parsed: _ParsedInput, source: int) -> list[float]:
    n = parsed.v_count
    dist: list[float] = [_INF] * n
    dist[source] = 0
    for _ in range(n - 1):
        updated = False
        for e in parsed.edges:
            if dist[e.u] != _INF and dist[e.u] + e.w < dist[e.v]:
                dist[e.v] = dist[e.u] + e.w
                updated = True
        if not updated:
            break
    return dist


def _all_pairs_via_bellman_ford(parsed: _ParsedInput) -> list[list[float]]:
    return [_bellman_ford_single_source(parsed, s) for s in range(parsed.v_count)]


def _has_reachable_negative_cycle(parsed: _ParsedInput) -> bool:
    for s in range(parsed.v_count):
        dist = _bellman_ford_single_source(parsed, s)
        if any(
            dist[e.u] != _INF and dist[e.u] + e.w < dist[e.v] for e in parsed.edges
        ):
            return True
    return False


def _parse_output_matrix(output_str: str, n: int) -> list[list[int]] | None:
    lines = [line.strip() for line in output_str.strip().splitlines() if line.strip()]
    if len(lines) != n:
        all_tokens = output_str.split()
        if len(all_tokens) != n * n:
            return None
        try:
            flat = [int(t) for t in all_tokens]
        except ValueError:
            return None
        return [flat[i * n : (i + 1) * n] for i in range(n)]
    matrix: list[list[int]] = []
    for line in lines:
        tokens = line.split()
        if len(tokens) != n:
            return None
        try:
            matrix.append([int(t) for t in tokens])
        except ValueError:
            return None
    return matrix


def _evidence(
    parsed: _ParsedInput, *, extra: dict[str, str] | None = None
) -> dict[str, str]:
    base = {"V": str(parsed.v_count), "E": str(len(parsed.edges))}
    if extra:
        base.update(extra)
    return base


class FloydWarshallVerifier:
    """Floyd-Warshall symbolic verifier (V × Bellman-Ford cross-check, V <= 25)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.FLOYD_WARSHALL

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
        n = parsed.v_count
        matrix = _parse_output_matrix(output_str, n)
        if matrix is None:
            return InvariantViolation(
                invariant_kind="output_is_v_by_v_matrix",
                description=f"sample {i}: output is not a {n}x{n} integer matrix",
                evidence=_evidence(parsed, extra={"output": output_str[:60]}),
            )
        for k in range(n):
            if matrix[k][k] != 0:
                return InvariantViolation(
                    invariant_kind="diagonal_is_zero",
                    description=(
                        f"sample {i}: diagonal d[{k + 1}][{k + 1}]={matrix[k][k]} "
                        f"!= 0"
                    ),
                    evidence=_evidence(
                        parsed, extra={"position": str(k), "value": str(matrix[k][k])}
                    ),
                )
        golden = _all_pairs_via_bellman_ford(parsed)
        for a in range(n):
            for b in range(n):
                exp_f = golden[a][b]
                act = matrix[a][b]
                if exp_f == _INF:
                    if act != -1:
                        return InvariantViolation(
                            invariant_kind="matches_bellman_ford_golden",
                            description=(
                                f"sample {i}: d[{a + 1}][{b + 1}]={act} but "
                                f"golden=unreachable (-1 expected)"
                            ),
                            evidence=_evidence(
                                parsed,
                                extra={
                                    "i": str(a + 1),
                                    "j": str(b + 1),
                                    "actual": str(act),
                                },
                            ),
                        )
                else:
                    exp = int(exp_f)
                    if act != exp:
                        return InvariantViolation(
                            invariant_kind="matches_bellman_ford_golden",
                            description=(
                                f"sample {i}: d[{a + 1}][{b + 1}]={act} != "
                                f"bellman_ford_golden={exp}"
                            ),
                            evidence=_evidence(
                                parsed,
                                extra={
                                    "i": str(a + 1),
                                    "j": str(b + 1),
                                    "actual": str(act),
                                    "golden": str(exp),
                                },
                            ),
                        )
        for a in range(n):
            for b in range(n):
                for k in range(n):
                    if matrix[a][k] == -1 or matrix[k][b] == -1:
                        continue
                    if matrix[a][b] == -1:
                        continue
                    if matrix[a][b] > matrix[a][k] + matrix[k][b]:
                        return InvariantViolation(
                            invariant_kind="triangle_inequality",
                            description=(
                                f"sample {i}: d[{a + 1}][{b + 1}]="
                                f"{matrix[a][b]} > d[{a + 1}][{k + 1}] + "
                                f"d[{k + 1}][{b + 1}] = "
                                f"{matrix[a][k] + matrix[k][b]}"
                            ),
                            evidence=_evidence(
                                parsed,
                                extra={
                                    "i": str(a + 1),
                                    "j": str(b + 1),
                                    "k": str(k + 1),
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
