"""Comparison Sort symbolic verifier — D안 Phase 2b PR-C5.

variant: **classic ascending comparison sort** (quicksort, mergesort, heapsort
family). Input N 개 정수 → output 동일 multiset 의 ascending 정렬.

Python ``sorted()`` golden 으로 cross-check — verifier 와 LLM 구현이 다른
algorithm (quicksort vs mergesort vs heapsort) 일 수 있으나 결과는 unique.

Invariants (4):
1. ``output_length_matches_n``: 출력 정수 갯수 == N.
2. ``output_preserves_input_multiset``: 출력 multiset == 입력 multiset.
3. ``output_is_sorted_ascending``: a[i] <= a[i+1] (non-strict).
4. ``output_matches_python_sorted``: ``output == sorted(input)``.

#4 가 #2 + #3 을 implies — invariant breakdown 의 explicit signal 목적.

Input format (1-indexed)::

    N
    a_1 a_2 ... a_N

Output: ``b_1 b_2 ... b_N`` ascending (whitespace-tolerant).
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


@dataclass(frozen=True)
class _ParsedInput:
    n: int
    values: tuple[int, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    tokens = text.split()
    if len(tokens) < 1:
        return None
    try:
        n = int(tokens[0])
    except ValueError:
        return None
    if n < 0:
        return None
    if len(tokens) - 1 != n:
        return None
    try:
        values = tuple(int(t) for t in tokens[1:])
    except ValueError:
        return None
    return _ParsedInput(n=n, values=values)


def _parse_output_ints(output_str: str, expected_n: int) -> list[int] | None:
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
    base = {"N": str(parsed.n)}
    if extra:
        base.update(extra)
    return base


class SortVerifier:
    """Comparison Sort symbolic verifier (ascending, Python sorted() golden)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.SORT

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
        actuals = _parse_output_ints(output_str, parsed.n)
        if actuals is None:
            return InvariantViolation(
                invariant_kind="output_length_matches_n",
                description=(
                    f"sample {i}: output integer count != N ({parsed.n})"
                ),
                evidence=_evidence(parsed),
            )
        if sorted(actuals) != sorted(parsed.values):
            return InvariantViolation(
                invariant_kind="output_preserves_input_multiset",
                description=f"sample {i}: output multiset != input multiset",
                evidence=_evidence(
                    parsed,
                    extra={"actual_sorted": str(sorted(actuals))[:80]},
                ),
            )
        for j in range(len(actuals) - 1):
            if actuals[j] > actuals[j + 1]:
                return InvariantViolation(
                    invariant_kind="output_is_sorted_ascending",
                    description=(
                        f"sample {i}: position {j} ({actuals[j]}) > "
                        f"position {j + 1} ({actuals[j + 1]})"
                    ),
                    evidence=_evidence(
                        parsed,
                        extra={
                            "position": str(j),
                            "actual_window": str(actuals[j : j + 2]),
                        },
                    ),
                )
        expected = sorted(parsed.values)
        if actuals != expected:
            return InvariantViolation(
                invariant_kind="output_matches_python_sorted",
                description=f"sample {i}: output != sorted(input)",
                evidence=_evidence(
                    parsed,
                    extra={
                        "actual": str(actuals)[:80],
                        "expected": str(expected)[:80],
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
