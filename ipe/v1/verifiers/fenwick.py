"""Fenwick Tree (Binary Indexed Tree) symbolic verifier — D안 Phase 2c PR-D5.

variant: **point-add + prefix-sum**. SegTree (PR-B2, assign + range sum) 와
다른 invariant pattern. operations:
- ``A i v``: add v to a[i] (1-indexed)
- ``Q i``: prefix sum a[1..i] (1-indexed inclusive)

Output: Q op 마다 한 줄, prefix sum value.

Cross-algorithm golden: **naive O(NQ) Python list cumulative sum**. 안전 상한
N,Q <= 1000.

DS family 3개째 — SegTree, Heap, **Fenwick** = 다른 invariant pattern (range-
assign / heap-ordered / point-add+prefix-sum).

Invariants (4):
1. ``output_count_matches_queries``: Q op 갯수 == output line count.
2. ``query_output_integer``: 모든 output token integer.
3. ``prefix_sum_non_negative_for_non_negative_input``: 초기 array + add v 모두
   >= 0 이면 모든 Q 결과 >= 0.
4. ``prefix_sum_matches_naive``: output[k] == naive prefix sum.

Input format (1-indexed)::

    N Q
    a_1 a_2 ... a_N
    op_1
    ...
    op_Q

op = "A i v" (add) | "Q i" (prefix sum).

Output: Q op 마다 한 줄, 단일 정수.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..schema import (
    AlgorithmDesign,
    InvariantViolation,
    ProblemSpec,
    SolutionAttempt,
    TargetAlgorithm,
)

_BRUTE_LIMIT = 1000

OpKind = Literal["A", "Q"]


@dataclass(frozen=True)
class _Op:
    kind: OpKind
    i: int
    v: int | None


@dataclass(frozen=True)
class _ParsedInput:
    n: int
    q: int
    initial: tuple[int, ...]
    ops: tuple[_Op, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    first = lines[0].split()
    if len(first) != 2:
        return None
    try:
        n, q = (int(x) for x in first)
    except ValueError:
        return None
    if n <= 0 or n > _BRUTE_LIMIT or q < 0 or q > _BRUTE_LIMIT:
        return None
    arr_tokens = lines[1].split()
    if len(arr_tokens) != n:
        return None
    try:
        initial = tuple(int(t) for t in arr_tokens)
    except ValueError:
        return None
    if len(lines) - 2 != q:
        return None
    ops: list[_Op] = []
    for line in lines[2:]:
        parts = line.split()
        if not parts:
            return None
        kind_raw = parts[0]
        if kind_raw == "A":
            if len(parts) != 3:
                return None
            try:
                i_raw = int(parts[1])
                v_raw = int(parts[2])
            except ValueError:
                return None
            if not (1 <= i_raw <= n):
                return None
            ops.append(_Op(kind="A", i=i_raw - 1, v=v_raw))
        elif kind_raw == "Q":
            if len(parts) != 2:
                return None
            try:
                i_raw = int(parts[1])
            except ValueError:
                return None
            if not (1 <= i_raw <= n):
                return None
            ops.append(_Op(kind="Q", i=i_raw - 1, v=None))
        else:
            return None
    return _ParsedInput(n=n, q=q, initial=initial, ops=tuple(ops))


def _naive_simulate(parsed: _ParsedInput) -> list[int]:
    arr = list(parsed.initial)
    outputs: list[int] = []
    for op in parsed.ops:
        if op.kind == "A":
            assert op.v is not None
            arr[op.i] += op.v
        else:
            outputs.append(sum(arr[: op.i + 1]))
    return outputs


def _parse_output_ints(output_str: str, expected_count: int) -> list[int] | None:
    tokens = output_str.split()
    if len(tokens) != expected_count:
        return None
    try:
        return [int(t) for t in tokens]
    except ValueError:
        return None


def _all_non_negative_inputs(parsed: _ParsedInput) -> bool:
    if any(x < 0 for x in parsed.initial):
        return False
    return all(op.v is None or op.v >= 0 for op in parsed.ops)


def _evidence(
    parsed: _ParsedInput, *, extra: dict[str, str] | None = None
) -> dict[str, str]:
    query_count = sum(1 for op in parsed.ops if op.kind == "Q")
    base = {"N": str(parsed.n), "Q": str(parsed.q), "queries": str(query_count)}
    if extra:
        base.update(extra)
    return base


class FenwickVerifier:
    """Fenwick Tree symbolic verifier (naive prefix-sum golden, N,Q <= 1000)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.FENWICK

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
        query_count = sum(1 for op in parsed.ops if op.kind == "Q")
        actuals = _parse_output_ints(output_str, query_count)
        if actuals is None:
            return InvariantViolation(
                invariant_kind="output_count_matches_queries",
                description=(
                    f"sample {i}: output token count != Q op count ({query_count})"
                ),
                evidence=_evidence(parsed, extra={"output": output_str[:60]}),
            )
        if _all_non_negative_inputs(parsed) and any(v < 0 for v in actuals):
            return InvariantViolation(
                invariant_kind="prefix_sum_non_negative_for_non_negative_input",
                description=f"sample {i}: all inputs >= 0 but some output < 0",
                evidence=_evidence(
                    parsed, extra={"negative_output_preview": str(actuals[:10])}
                ),
            )
        golden = _naive_simulate(parsed)
        if actuals != golden:
            return InvariantViolation(
                invariant_kind="prefix_sum_matches_naive",
                description=f"sample {i}: output != naive prefix-sum simulation",
                evidence=_evidence(
                    parsed,
                    extra={
                        "actual_preview": str(actuals[:10]),
                        "golden_preview": str(golden[:10]),
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
