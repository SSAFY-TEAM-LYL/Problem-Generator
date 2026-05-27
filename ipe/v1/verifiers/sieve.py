"""Sieve of Eratosthenes symbolic verifier — D안 Phase 2b PR-C8.

variant: **enumerate all primes p, 2 <= p <= N**. ascending. Sieve / Linear
Sieve / Wheel Sieve family 모두 cover.

Golden: **trial division** O(N √N). 안전 상한 ``N <= 10000``.

Invariants (4):
1. ``output_is_int_list``: 모든 출력 token 이 정수.
2. ``all_in_valid_range``: 모든 p 가 ``2 <= p <= N``.
3. ``all_strictly_ascending``: ``p_i < p_{i+1}``.
4. ``matches_trial_division``: output multiset+order == trial division golden.

Input format::

    N

(단일 정수, ``0 <= N <= 10000``)

Output: ascending primes, space-separated (whitespace-tolerant). ``N < 2`` 면 empty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..schema import (
    AlgorithmDesign,
    InvariantViolation,
    ProblemSpec,
    SolutionAttempt,
    TargetAlgorithm,
)

_TRIAL_N_LIMIT = 10_000


@dataclass(frozen=True)
class _ParsedInput:
    n: int


def _parse_sample_input(text: str) -> _ParsedInput | None:
    tokens = text.split()
    if len(tokens) != 1:
        return None
    try:
        n = int(tokens[0])
    except ValueError:
        return None
    if n < 0 or n > _TRIAL_N_LIMIT:
        return None
    return _ParsedInput(n=n)


def _trial_division_primes(n: int) -> list[int]:
    if n < 2:
        return []
    primes: list[int] = []
    for i in range(2, n + 1):
        is_prime = True
        for d in range(2, int(math.isqrt(i)) + 1):
            if i % d == 0:
                is_prime = False
                break
        if is_prime:
            primes.append(i)
    return primes


def _parse_output_ints(output_str: str) -> list[int] | None:
    tokens = output_str.split()
    if not tokens:
        return []
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


class SieveVerifier:
    """Sieve of Eratosthenes symbolic verifier (trial division golden)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.SIEVE

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
        actuals = _parse_output_ints(output_str)
        if actuals is None:
            return InvariantViolation(
                invariant_kind="output_is_int_list",
                description=f"sample {i}: output contains non-integer token",
                evidence=_evidence(parsed, extra={"output": output_str[:60]}),
            )
        for j, p in enumerate(actuals):
            if not (2 <= p <= parsed.n):
                return InvariantViolation(
                    invariant_kind="all_in_valid_range",
                    description=(
                        f"sample {i}: actuals[{j}]={p} not in [2..{parsed.n}]"
                    ),
                    evidence=_evidence(
                        parsed, extra={"position": str(j), "value": str(p)}
                    ),
                )
        for j in range(len(actuals) - 1):
            if actuals[j] >= actuals[j + 1]:
                return InvariantViolation(
                    invariant_kind="all_strictly_ascending",
                    description=(
                        f"sample {i}: position {j} ({actuals[j]}) >= "
                        f"position {j + 1} ({actuals[j + 1]})"
                    ),
                    evidence=_evidence(parsed, extra={"position": str(j)}),
                )
        expected = _trial_division_primes(parsed.n)
        if actuals != expected:
            return InvariantViolation(
                invariant_kind="matches_trial_division",
                description=(
                    f"sample {i}: output != trial_division golden "
                    f"(len {len(actuals)} vs {len(expected)})"
                ),
                evidence=_evidence(
                    parsed,
                    extra={
                        "actual_len": str(len(actuals)),
                        "expected_len": str(len(expected)),
                        "expected_preview": str(expected[:10]),
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
