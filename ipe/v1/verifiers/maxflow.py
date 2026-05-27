"""Maximum Flow symbolic verifier — D안 Phase 2b PR-C7.

variant: **classic single-source single-sink max flow** in directed graph with
non-negative integer capacities. Output: 단일 정수 — max flow s→t.

Cluster verifier: Ford-Fulkerson / Edmonds-Karp / Dinic family (verifier 는
결과만 봄, algorithm 선택은 designer 자유).

Golden: **brute min-cut via subset enumeration** (max-flow min-cut theorem).
Enumerate 2^(V-2) subsets S ⊆ V \\ {s, t} 의 augmented partition (s∈S, t∈T) 의
cut capacity. min capacity = max flow. O(2^V * E). 안전 상한 V <= 14.

Invariants (4):
1. ``output_is_single_int``: 단일 정수.
2. ``flow_non_negative``: flow >= 0.
3. ``flow_within_source_outflow``: flow <= sum(cap_i for edge leaving s).
4. ``flow_matches_brute_min_cut``: flow == brute min-cut golden.

Input format (1-indexed)::

    V E s t
    u_1 v_1 c_1
    ...
    u_E v_E c_E

Output: 단일 정수.
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

_BRUTE_V_LIMIT = 14


@dataclass(frozen=True)
class _Edge:
    u: int
    v: int
    cap: int


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
    if v_count < 2 or v_count > _BRUTE_V_LIMIT or e_count < 0:
        return None
    if not (1 <= s_raw <= v_count and 1 <= t_raw <= v_count) or s_raw == t_raw:
        return None
    if len(lines) - 1 != e_count:
        return None
    edges: list[_Edge] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) != 3:
            return None
        try:
            u_raw, v_raw, c_raw = (int(x) for x in parts)
        except ValueError:
            return None
        if not (1 <= u_raw <= v_count and 1 <= v_raw <= v_count):
            return None
        if c_raw < 0:
            return None
        edges.append(_Edge(u=u_raw - 1, v=v_raw - 1, cap=c_raw))
    return _ParsedInput(
        v_count=v_count, s=s_raw - 1, t=t_raw - 1, edges=tuple(edges)
    )


def _brute_min_cut(parsed: _ParsedInput) -> int:
    n = parsed.v_count
    s, t = parsed.s, parsed.t
    others = [i for i in range(n) if i != s and i != t]
    best = -1
    for mask in range(1 << len(others)):
        in_s: set[int] = {s}
        for k, node in enumerate(others):
            if mask & (1 << k):
                in_s.add(node)
        cut_cap = 0
        for e in parsed.edges:
            if e.u in in_s and e.v not in in_s:
                cut_cap += e.cap
        if best < 0 or cut_cap < best:
            best = cut_cap
    return best if best >= 0 else 0


def _source_outflow_bound(parsed: _ParsedInput) -> int:
    return sum(e.cap for e in parsed.edges if e.u == parsed.s)


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


class MaxFlowVerifier:
    """Maximum Flow symbolic verifier (brute min-cut golden, V <= 14)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.MAX_FLOW

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
        if actual < 0:
            return InvariantViolation(
                invariant_kind="flow_non_negative",
                description=f"sample {i}: output={actual} < 0",
                evidence=_evidence(parsed, extra={"actual": str(actual)}),
            )
        bound = _source_outflow_bound(parsed)
        if actual > bound:
            return InvariantViolation(
                invariant_kind="flow_within_source_outflow",
                description=(
                    f"sample {i}: output={actual} > source outflow bound={bound}"
                ),
                evidence=_evidence(
                    parsed, extra={"actual": str(actual), "bound": str(bound)}
                ),
            )
        expected = _brute_min_cut(parsed)
        if actual != expected:
            return InvariantViolation(
                invariant_kind="flow_matches_brute_min_cut",
                description=(
                    f"sample {i}: output={actual} != brute_min_cut={expected}"
                ),
                evidence=_evidence(
                    parsed,
                    extra={
                        "actual": str(actual),
                        "brute_min_cut": str(expected),
                    },
                ),
            )
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
