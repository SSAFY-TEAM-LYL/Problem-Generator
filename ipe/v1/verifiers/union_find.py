"""Union-Find (Disjoint Set Union) symbolic verifier — D안 Phase 2b PR-C2.

variant: **classic same-set query**. N elements (1-indexed) 모두 별도 set 으로
시작. Two ops:
- ``U x y``: union x's set and y's set (no output).
- ``Q x y``: same-set query, output 0 or 1.

Invariants (4):
1. ``output_count_matches_queries``: 출력 줄 수 == input 의 ``Q`` op 갯수.
2. ``binary_output_for_queries``: 모든 출력 ∈ {0, 1}.
3. ``same_set_correctness``: BFS over union edges (naive O(N) per query) 와 일치.
4. ``self_query_returns_one``: ``Q x x`` 는 항상 1.

Input format (1-indexed)::

    N Q
    op_1
    ...
    op_Q

Output: 각 ``Q`` op 마다 한 줄, ``0`` 또는 ``1``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from ..schema import (
    AlgorithmDesign,
    InvariantViolation,
    ProblemSpec,
    SolutionAttempt,
    TargetAlgorithm,
)

OpKind = Literal["U", "Q"]


@dataclass(frozen=True)
class _Op:
    kind: OpKind
    x: int  # 0-indexed internal
    y: int


@dataclass(frozen=True)
class _ParsedInput:
    n: int
    ops: tuple[_Op, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 1:
        return None
    first = lines[0].split()
    if len(first) != 2:
        return None
    try:
        n = int(first[0])
        q = int(first[1])
    except ValueError:
        return None
    if n <= 0 or q < 0:
        return None
    if len(lines) - 1 != q:
        return None
    ops: list[_Op] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) != 3:
            return None
        kind = parts[0]
        if kind not in ("U", "Q"):
            return None
        try:
            x_raw = int(parts[1])
            y_raw = int(parts[2])
        except ValueError:
            return None
        if not (1 <= x_raw <= n and 1 <= y_raw <= n):
            return None
        op_kind: OpKind = "U" if kind == "U" else "Q"
        ops.append(_Op(kind=op_kind, x=x_raw - 1, y=y_raw - 1))
    return _ParsedInput(n=n, ops=tuple(ops))


def _simulate_naive_same(parsed: _ParsedInput) -> list[int]:
    adj: list[set[int]] = [set() for _ in range(parsed.n)]
    outputs: list[int] = []
    for op in parsed.ops:
        if op.kind == "U":
            adj[op.x].add(op.y)
            adj[op.y].add(op.x)
        else:
            if op.x == op.y:
                outputs.append(1)
                continue
            visited: set[int] = {op.x}
            queue: deque[int] = deque([op.x])
            found = False
            while queue and not found:
                u = queue.popleft()
                for v in adj[u]:
                    if v == op.y:
                        found = True
                        break
                    if v not in visited:
                        visited.add(v)
                        queue.append(v)
            outputs.append(1 if found else 0)
    return outputs


def _parse_output_lines(output_str: str, expected_count: int) -> list[int] | None:
    lines = [line.strip() for line in output_str.strip().splitlines() if line.strip()]
    if len(lines) != expected_count:
        return None
    try:
        return [int(x) for x in lines]
    except ValueError:
        return None


def _evidence(
    parsed: _ParsedInput, *, extra: dict[str, str] | None = None
) -> dict[str, str]:
    query_count = sum(1 for op in parsed.ops if op.kind == "Q")
    base = {
        "N": str(parsed.n),
        "ops_count": str(len(parsed.ops)),
        "query_count": str(query_count),
    }
    if extra:
        base.update(extra)
    return base


class UnionFindVerifier:
    """Union-Find (DSU same-set) specific symbolic verifier."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.UNION_FIND

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
            expected_query_count = sum(1 for op in parsed.ops if op.kind == "Q")
            actuals = _parse_output_lines(output_str, expected_query_count)
            if actuals is None:
                violations.append(
                    InvariantViolation(
                        invariant_kind="output_count_matches_queries",
                        description=(
                            f"sample {i}: output line count != query op count "
                            f"({expected_query_count})"
                        ),
                        evidence=_evidence(parsed),
                    )
                )
                continue
            sample_violation = self._check_sample(i, parsed, actuals)
            if sample_violation is not None:
                violations.append(sample_violation)
        return violations

    def _check_sample(
        self, i: int, parsed: _ParsedInput, actuals: list[int]
    ) -> InvariantViolation | None:
        for j, val in enumerate(actuals):
            if val not in (0, 1):
                return InvariantViolation(
                    invariant_kind="binary_output_for_queries",
                    description=(
                        f"sample {i}: query {j} actual={val} not in {{0, 1}}"
                    ),
                    evidence=_evidence(
                        parsed, extra={"query_idx": str(j), "actual": str(val)}
                    ),
                )
        golden = _simulate_naive_same(parsed)
        for j, (actual, expected) in enumerate(zip(actuals, golden, strict=True)):
            if actual != expected:
                return InvariantViolation(
                    invariant_kind="same_set_correctness",
                    description=(
                        f"sample {i}: query {j} actual={actual} != "
                        f"naive_golden={expected}"
                    ),
                    evidence=_evidence(
                        parsed,
                        extra={
                            "query_idx": str(j),
                            "actual": str(actual),
                            "naive_golden": str(expected),
                        },
                    ),
                )
        query_op_idx = 0
        for op in parsed.ops:
            if op.kind != "Q":
                continue
            if op.x == op.y and actuals[query_op_idx] != 1:
                return InvariantViolation(
                    invariant_kind="self_query_returns_one",
                    description=(
                        f"sample {i}: Q {op.x + 1} {op.x + 1} (self-query) "
                        f"actual={actuals[query_op_idx]}, expected 1"
                    ),
                    evidence=_evidence(parsed, extra={"query_idx": str(query_op_idx)}),
                )
            query_op_idx += 1
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
