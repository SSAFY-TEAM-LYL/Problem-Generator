"""Segment Tree symbolic verifier — D안 Phase 2a PR-B2.

variant: **Range Sum + Point Update** (Phase 2a 단순화). Range Min/Max /
Range Update + Lazy propagation 등 다른 variant 는 Phase 3 에서 enum 확장 +
별도 verifier 검토.

Invariants (4):
1. ``output_count_matches_queries``: 출력 줄 수 == input 의 ``Q l r`` operation
   갯수.
2. ``non_negative_sum_for_non_negative_input``: 입력 ``a_i`` 가 모두 >= 0 이고
   업데이트 ``v`` 도 >= 0 이면 모든 query 결과 >= 0.
3. ``range_sum_optimal``: naive O(N) per-query Python list 시뮬레이터 결과와
   각 query 마다 정확 일치 (모든 update 반영 후).
4. ``single_element_query_consistency``: ``l == r`` 일 때 결과 == 그 시점
   ``array[l]``.

Input format (Phase 2a 단순화 — competitive programming 표준 따라 **1-indexed**)::

    N Q
    a_1 a_2 ... a_N
    op_1
    op_2
    ...
    op_Q

각 op_i 형식 (모두 1-indexed):
- ``U i v`` : ``A[i] = v`` (point update, 1<=i<=N)
- ``Q l r`` : sum(A[l..r]) 출력 (inclusive, 1<=l<=r<=N)

Output format: ``Q l r`` 마다 한 줄, 단일 정수. ``U`` 는 출력 없음.

PR-B2.1 fix: 첫 smoke run 에서 LLM 의 자연 format (1-indexed, "N Q" 한 줄)
과 verifier 의 strict 0-indexed format mismatch 로 ``samples_engaged=0``
관측됨. verifier 가 LLM 자연 format 따르도록 rewrite (internal 은 0-indexed 로
변환).

format mismatch / parse 실패 시 verifier silent skip — executor sample exact
match fallback.
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

OpKind = Literal["U", "Q"]


@dataclass(frozen=True)
class _Op:
    """parsed operation. U: (kind='U', i, v); Q: (kind='Q', l, r)."""

    kind: OpKind
    a: int
    b: int


@dataclass(frozen=True)
class _ParsedInput:
    n: int
    arr: tuple[int, ...]
    ops: tuple[_Op, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    """"N Q" first line + array + Q ops (1-indexed). 실패 시 None.

    Internal storage 는 0-indexed (op.a, op.b) — verifier 의 simulation 단순화.
    1→0 변환은 본 함수에서만.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
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
    if len(lines) != 2 + q:
        return None
    try:
        values = tuple(int(x) for x in lines[1].split())
    except ValueError:
        return None
    if len(values) != n:
        return None
    ops: list[_Op] = []
    for line in lines[2 : 2 + q]:
        parts = line.split()
        if len(parts) != 3:
            return None
        kind = parts[0]
        if kind not in ("U", "Q"):
            return None
        try:
            a_raw = int(parts[1])
            b_raw = int(parts[2])
        except ValueError:
            return None
        if kind == "U":
            i_0 = a_raw - 1
            if not (0 <= i_0 < n):
                return None
            ops.append(_Op(kind="U", a=i_0, b=b_raw))
        else:  # Q
            l_0 = a_raw - 1
            r_0 = b_raw - 1
            if not (0 <= l_0 <= r_0 < n):
                return None
            ops.append(_Op(kind="Q", a=l_0, b=r_0))
    return _ParsedInput(n=n, arr=values, ops=tuple(ops))


def _simulate_naive(parsed: _ParsedInput) -> list[int]:
    """naive O(NQ) — 각 query 마다 Python sum. golden anchor."""
    arr = list(parsed.arr)
    outputs: list[int] = []
    for op in parsed.ops:
        if op.kind == "U":
            arr[op.a] = op.b
        else:  # Q
            outputs.append(sum(arr[op.a : op.b + 1]))
    return outputs


def _parse_output_lines(output_str: str, expected_count: int) -> list[int] | None:
    """output 의 query 갯수 줄 parse. count mismatch 또는 non-int 면 None."""
    lines = [line.strip() for line in output_str.strip().splitlines() if line.strip()]
    if len(lines) != expected_count:
        return None
    try:
        return [int(x) for x in lines]
    except ValueError:
        return None


def _array_snapshot_at_query(parsed: _ParsedInput, query_idx_in_ops: int) -> list[int]:
    """query_idx_in_ops 시점의 array 상태 (그 query 직전까지의 update 반영)."""
    arr = list(parsed.arr)
    for i, op in enumerate(parsed.ops):
        if i == query_idx_in_ops:
            return arr
        if op.kind == "U":
            arr[op.a] = op.b
    return arr


def _evidence(
    parsed: _ParsedInput, *, extra: dict[str, str] | None = None
) -> dict[str, str]:
    arr_preview = " ".join(str(x) for x in parsed.arr[:10])
    if parsed.n > 10:
        arr_preview += " ..."
    query_count = sum(1 for op in parsed.ops if op.kind == "Q")
    base = {
        "N": str(parsed.n),
        "arr_preview": arr_preview,
        "ops_count": str(len(parsed.ops)),
        "query_count": str(query_count),
    }
    if extra:
        base.update(extra)
    return base


class SegmentTreeVerifier:
    """Segment Tree (Range Sum + Point Update) specific symbolic verifier."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.SEGTREE

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
        # non_negative_sum_for_non_negative_input
        all_inputs_non_negative = all(x >= 0 for x in parsed.arr) and all(
            op.b >= 0 for op in parsed.ops if op.kind == "U"
        )
        if all_inputs_non_negative:
            for j, val in enumerate(actuals):
                if val < 0:
                    return InvariantViolation(
                        invariant_kind="non_negative_sum_for_non_negative_input",
                        description=(
                            f"sample {i}: query {j} actual={val} < 0 but all "
                            "inputs >= 0"
                        ),
                        evidence=_evidence(
                            parsed, extra={"query_idx": str(j), "actual": str(val)}
                        ),
                    )
        # range_sum_optimal (naive cross-check)
        golden = _simulate_naive(parsed)
        for j, (actual, expected) in enumerate(zip(actuals, golden, strict=True)):
            if actual != expected:
                return InvariantViolation(
                    invariant_kind="range_sum_optimal",
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
        # single_element_query_consistency
        query_op_idx = 0
        for op_idx, op in enumerate(parsed.ops):
            if op.kind != "Q":
                continue
            if op.a == op.b:
                snapshot = _array_snapshot_at_query(parsed, op_idx)
                expected_single = snapshot[op.a]
                if actuals[query_op_idx] != expected_single:
                    return InvariantViolation(
                        invariant_kind="single_element_query_consistency",
                        description=(
                            f"sample {i}: query {query_op_idx} (l=r={op.a}) "
                            f"actual={actuals[query_op_idx]} != "
                            f"array[{op.a}]={expected_single}"
                        ),
                        evidence=_evidence(
                            parsed,
                            extra={
                                "query_idx": str(query_op_idx),
                                "index": str(op.a),
                            },
                        ),
                    )
            query_op_idx += 1
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        """parse 가능한 sample 수 — H1 측정 verifier 실효성 신호."""
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
