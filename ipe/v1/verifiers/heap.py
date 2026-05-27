"""Min-Heap (Priority Queue) symbolic verifier — D안 Phase 2c PR-D4.

variant: **classic min-heap operation sequence**. Operations:
- ``P x``: push integer x.
- ``O``: pop min (and output value).

Output: pop op 마다 한 줄, popped value.

Cross-algorithm golden: **naive sorted list simulation** (O(N^2)) —
binary-heap 과 다른 implementation. 안전 상한 N <= 1000.

DS family 시작 — SegTree (PR-B2) 다음으로 두 번째 DS verifier.

Invariants (4):
1. ``output_count_matches_pops``: pop op 갯수 == output line 수.
2. ``popped_values_are_ints``: 모든 output token integer parseable.
3. ``all_popped_in_pushed_multiset``: 모든 popped value 가 push 된 multiset 안.
4. ``matches_naive_min_heap_golden``: output == sorted-list simulation 결과.

Input format::

    N
    op_1
    op_2
    ...
    op_N

(op = "P x" (push) | "O" (pop min). pop on empty heap 금지.)

Output: pop op 마다 한 줄, 단일 정수 (whitespace-tolerant).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from ..schema import (
    AlgorithmDesign,
    InvariantViolation,
    ProblemSpec,
    SolutionAttempt,
    TargetAlgorithm,
)

_BRUTE_N_LIMIT = 1000

OpKind = Literal["P", "O"]


@dataclass(frozen=True)
class _Op:
    kind: OpKind
    value: int | None  # None for pop


@dataclass(frozen=True)
class _ParsedInput:
    n: int
    ops: tuple[_Op, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 1:
        return None
    try:
        n = int(lines[0])
    except ValueError:
        return None
    if n < 0 or n > _BRUTE_N_LIMIT:
        return None
    if len(lines) - 1 != n:
        return None
    ops: list[_Op] = []
    heap_size = 0
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            return None
        kind_raw = parts[0]
        if kind_raw == "P":
            if len(parts) != 2:
                return None
            try:
                x = int(parts[1])
            except ValueError:
                return None
            ops.append(_Op(kind="P", value=x))
            heap_size += 1
        elif kind_raw == "O":
            if len(parts) != 1:
                return None
            if heap_size <= 0:
                return None
            ops.append(_Op(kind="O", value=None))
            heap_size -= 1
        else:
            return None
    return _ParsedInput(n=n, ops=tuple(ops))


def _naive_min_heap_golden(parsed: _ParsedInput) -> list[int]:
    heap: list[int] = []
    outputs: list[int] = []
    for op in parsed.ops:
        if op.kind == "P":
            assert op.value is not None
            heap.append(op.value)
        else:
            m = min(heap)
            heap.remove(m)
            outputs.append(m)
    return outputs


def _parse_output_ints(output_str: str, expected_count: int) -> list[int] | None:
    tokens = output_str.split()
    if len(tokens) != expected_count:
        return None
    try:
        return [int(t) for t in tokens]
    except ValueError:
        return None


def _evidence(
    parsed: _ParsedInput, *, extra: dict[str, str] | None = None
) -> dict[str, str]:
    push_count = sum(1 for op in parsed.ops if op.kind == "P")
    pop_count = sum(1 for op in parsed.ops if op.kind == "O")
    base = {
        "N": str(parsed.n),
        "pushes": str(push_count),
        "pops": str(pop_count),
    }
    if extra:
        base.update(extra)
    return base


class HeapVerifier:
    """Min-Heap symbolic verifier (sorted-list simulation golden, N <= 1000)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.HEAP

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
        pop_count = sum(1 for op in parsed.ops if op.kind == "O")
        actuals = _parse_output_ints(output_str, pop_count)
        if actuals is None:
            return InvariantViolation(
                invariant_kind="output_count_matches_pops",
                description=(
                    f"sample {i}: output token count != pop op count ({pop_count})"
                ),
                evidence=_evidence(parsed, extra={"output": output_str[:60]}),
            )
        pushed_multiset = Counter(
            op.value for op in parsed.ops if op.kind == "P" and op.value is not None
        )
        actual_multiset = Counter(actuals)
        for val, cnt in actual_multiset.items():
            if pushed_multiset.get(val, 0) < cnt:
                return InvariantViolation(
                    invariant_kind="all_popped_in_pushed_multiset",
                    description=(
                        f"sample {i}: popped value {val} (x{cnt}) exceeds "
                        f"push count {pushed_multiset.get(val, 0)}"
                    ),
                    evidence=_evidence(
                        parsed, extra={"value": str(val), "popped_x": str(cnt)}
                    ),
                )
        golden = _naive_min_heap_golden(parsed)
        if actuals != golden:
            return InvariantViolation(
                invariant_kind="matches_naive_min_heap_golden",
                description=f"sample {i}: output != naive min-heap golden",
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
