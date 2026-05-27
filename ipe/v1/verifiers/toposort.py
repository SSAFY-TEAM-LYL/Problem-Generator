"""Topological Sort symbolic verifier — D안 Phase 2b PR-C3.

variant: **classic DAG topological ordering**. ``N`` nodes (1-indexed), ``M``
directed edges (u→v). Output: ``N`` integers — a permutation of ``{1..N}`` such
that for every edge ``u→v``, ``pos[u] < pos[v]``.

NB topo order is NOT unique → verifier checks *constraints*, not equality. Kahn's
algorithm 은 DAG 여부 (input validity) 만 확인.

Invariants (4):
1. ``output_length_matches_n``: output 줄의 정수 갯수 == N.
2. ``output_is_permutation``: output ∈ permutation of ``{1..N}`` (no dup, no OOB).
3. ``edges_respect_order``: ∀ edge u→v, ``pos[u] < pos[v]``.
4. ``dag_input_via_kahn``: input 자체가 DAG (Kahn 으로 cross-check). cycle 이면
   spec invalid → silent skip.

Input format (1-indexed)::

    N M
    u_1 v_1
    ...
    u_M v_M

Output: N space-separated 정수 (한 줄 또는 여러 줄, whitespace-tolerant).
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


@dataclass(frozen=True)
class _Edge:
    u: int  # 0-indexed internal
    v: int


@dataclass(frozen=True)
class _ParsedInput:
    n: int
    edges: tuple[_Edge, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 1:
        return None
    first = lines[0].split()
    if len(first) != 2:
        return None
    try:
        n = int(first[0])
        m = int(first[1])
    except ValueError:
        return None
    if n <= 0 or m < 0:
        return None
    if len(lines) - 1 != m:
        return None
    edges: list[_Edge] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) != 2:
            return None
        try:
            u_raw = int(parts[0])
            v_raw = int(parts[1])
        except ValueError:
            return None
        if not (1 <= u_raw <= n and 1 <= v_raw <= n):
            return None
        if u_raw == v_raw:
            return None
        edges.append(_Edge(u=u_raw - 1, v=v_raw - 1))
    return _ParsedInput(n=n, edges=tuple(edges))


def _kahn_is_dag(parsed: _ParsedInput) -> bool:
    adj: list[list[int]] = [[] for _ in range(parsed.n)]
    indeg = [0] * parsed.n
    for e in parsed.edges:
        adj[e.u].append(e.v)
        indeg[e.v] += 1
    queue: deque[int] = deque(i for i in range(parsed.n) if indeg[i] == 0)
    visited = 0
    while queue:
        u = queue.popleft()
        visited += 1
        for w in adj[u]:
            indeg[w] -= 1
            if indeg[w] == 0:
                queue.append(w)
    return visited == parsed.n


def _parse_output_perm(output_str: str, expected_n: int) -> list[int] | None:
    tokens = output_str.split()
    if len(tokens) != expected_n:
        return None
    try:
        return [int(t) for t in tokens]
    except ValueError:
        return None


def _evidence(
    parsed: _ParsedInput, *, extra: dict[str, str] | None = None
) -> dict[str, str]:
    base = {"N": str(parsed.n), "M": str(len(parsed.edges))}
    if extra:
        base.update(extra)
    return base


class TopologicalSortVerifier:
    """Topological Sort symbolic verifier (DAG ordering invariants)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.TOPOSORT

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
            if not _kahn_is_dag(parsed):
                continue
            sample_violation = self._check_sample(i, parsed, output_str)
            if sample_violation is not None:
                violations.append(sample_violation)
        return violations

    def _check_sample(
        self, i: int, parsed: _ParsedInput, output_str: str
    ) -> InvariantViolation | None:
        actuals = _parse_output_perm(output_str, parsed.n)
        if actuals is None:
            return InvariantViolation(
                invariant_kind="output_length_matches_n",
                description=(
                    f"sample {i}: output integer count != N ({parsed.n})"
                ),
                evidence=_evidence(parsed),
            )
        if sorted(actuals) != list(range(1, parsed.n + 1)):
            return InvariantViolation(
                invariant_kind="output_is_permutation",
                description=(
                    f"sample {i}: output is not a permutation of "
                    f"{{1..{parsed.n}}}"
                ),
                evidence=_evidence(
                    parsed, extra={"actual_sorted": str(sorted(actuals))[:80]}
                ),
            )
        pos = [0] * parsed.n
        for idx, val in enumerate(actuals):
            pos[val - 1] = idx
        for e in parsed.edges:
            if pos[e.u] >= pos[e.v]:
                return InvariantViolation(
                    invariant_kind="edges_respect_order",
                    description=(
                        f"sample {i}: edge {e.u + 1}->{e.v + 1} violated "
                        f"(pos[{e.u + 1}]={pos[e.u]} >= pos[{e.v + 1}]={pos[e.v]})"
                    ),
                    evidence=_evidence(
                        parsed,
                        extra={
                            "edge": f"{e.u + 1}->{e.v + 1}",
                            "pos_u": str(pos[e.u]),
                            "pos_v": str(pos[e.v]),
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
            if not _kahn_is_dag(parsed):
                continue
            engaged += 1
        return engaged
