"""0/1 Knapsack symbolic verifier — D안 Phase 2b PR-C4.

variant: **classic 0/1 Knapsack — maximum value subset under capacity**.
``N`` items (1-indexed), capacity ``C``. Each item has weight ``w_i >= 0`` and
value ``v_i >= 0``. Select subset S ⊆ ``1..N`` s.t. ``sum_{i∈S} w_i <= C`` and
``sum_{i∈S} v_i`` is maximized.

Output: 단일 정수 — maximum value.

Note: value 자체는 unique. reconstruction (chosen items) 은 non-unique 가능하나
V1 에서는 value 만 검증.

Invariants (4):
1. ``output_is_single_int``: output 이 단일 정수 (parse 가능).
2. ``value_non_negative``: output >= 0.
3. ``value_within_total_bound``: 0 <= output <= sum(v_i).
4. ``value_optimal_via_brute``: brute O(2^N) subset enum golden 과 일치. Sample
   ``N`` 작아야 (~12-15) — architect prompt 가 이 bound 강제.

Input format (1-indexed)::

    N C
    w_1 v_1
    ...
    w_N v_N

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

_BRUTE_N_LIMIT = 22


@dataclass(frozen=True)
class _Item:
    weight: int
    value: int


@dataclass(frozen=True)
class _ParsedInput:
    n: int
    capacity: int
    items: tuple[_Item, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 1:
        return None
    first = lines[0].split()
    if len(first) != 2:
        return None
    try:
        n = int(first[0])
        c = int(first[1])
    except ValueError:
        return None
    if n <= 0 or c < 0 or n > _BRUTE_N_LIMIT:
        return None
    if len(lines) - 1 != n:
        return None
    items: list[_Item] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) != 2:
            return None
        try:
            w = int(parts[0])
            v = int(parts[1])
        except ValueError:
            return None
        if w < 0 or v < 0:
            return None
        items.append(_Item(weight=w, value=v))
    return _ParsedInput(n=n, capacity=c, items=tuple(items))


def _brute_optimal(parsed: _ParsedInput) -> int:
    n = parsed.n
    weights = [it.weight for it in parsed.items]
    values = [it.value for it in parsed.items]
    best = 0
    for mask in range(1 << n):
        w_sum = 0
        v_sum = 0
        over = False
        for i in range(n):
            if mask & (1 << i):
                w_sum += weights[i]
                if w_sum > parsed.capacity:
                    over = True
                    break
                v_sum += values[i]
        if not over and v_sum > best:
            best = v_sum
    return best


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
        "N": str(parsed.n),
        "C": str(parsed.capacity),
        "total_value": str(sum(it.value for it in parsed.items)),
    }
    if extra:
        base.update(extra)
    return base


class KnapsackVerifier:
    """0/1 Knapsack symbolic verifier (max value, brute O(2^N) golden)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.KNAPSACK

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
                invariant_kind="value_non_negative",
                description=f"sample {i}: output={actual} < 0",
                evidence=_evidence(parsed, extra={"actual": str(actual)}),
            )
        total_value = sum(it.value for it in parsed.items)
        if actual > total_value:
            return InvariantViolation(
                invariant_kind="value_within_total_bound",
                description=(
                    f"sample {i}: output={actual} > sum(v_i)={total_value}"
                ),
                evidence=_evidence(parsed, extra={"actual": str(actual)}),
            )
        optimal = _brute_optimal(parsed)
        if actual != optimal:
            return InvariantViolation(
                invariant_kind="value_optimal_via_brute",
                description=(
                    f"sample {i}: output={actual} != brute_optimal={optimal}"
                ),
                evidence=_evidence(
                    parsed,
                    extra={"actual": str(actual), "brute_optimal": str(optimal)},
                ),
            )
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
