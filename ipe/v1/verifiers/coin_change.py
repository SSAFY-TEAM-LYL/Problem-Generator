"""Coin Change symbolic verifier — D안 Phase 2c PR-D6.

variant: **minimum coin count** to make amount A from coin denominations (each
coin can be used unlimited times). Output: 단일 정수 — min coins (또는 ``-1``
if impossible).

DP family 2개째 — Knapsack (PR-C4, outlier 1/3) 다음. DP O(N*A) golden 으로
cross-check. **Knapsack 의 architect expected_output 오류 패턴이 동일 DP
family 에서도 재현되는지 narrative anchor.**

Golden: DP O(N*A) tabulation. 안전 상한 ``A <= 1000``, ``N <= 20``.

Invariants (4):
1. ``output_is_single_int``: 단일 정수.
2. ``count_in_valid_range``: ``-1 또는 0 <= count <= A``.
3. ``existence_consistent_with_dp``: DP 도달가능성과 일치.
4. ``count_matches_dp_optimal``: output == DP min coins.

Input format (1-indexed)::

    N A
    c_1 c_2 ... c_N

(N = coin types, A = target amount, c_i >= 1)

Output: 단일 정수, ``-1`` 또는 minimum coin count.
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

_AMOUNT_LIMIT = 1000
_COINS_LIMIT = 20


@dataclass(frozen=True)
class _ParsedInput:
    n: int
    amount: int
    coins: tuple[int, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    first = lines[0].split()
    if len(first) != 2:
        return None
    try:
        n, a = (int(x) for x in first)
    except ValueError:
        return None
    if n <= 0 or n > _COINS_LIMIT or a < 0 or a > _AMOUNT_LIMIT:
        return None
    coins_tokens = lines[1].split()
    if len(coins_tokens) != n:
        return None
    try:
        coins = tuple(int(t) for t in coins_tokens)
    except ValueError:
        return None
    if any(c < 1 for c in coins):
        return None
    return _ParsedInput(n=n, amount=a, coins=coins)


def _dp_min_coins(parsed: _ParsedInput) -> int:
    """Return min coins for amount, or -1 if impossible. O(N * A)."""
    a = parsed.amount
    dp = [a + 1] * (a + 1)
    dp[0] = 0
    for amt in range(1, a + 1):
        for c in parsed.coins:
            if c <= amt and dp[amt - c] + 1 < dp[amt]:
                dp[amt] = dp[amt - c] + 1
    return dp[a] if dp[a] <= a else -1


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
        "A": str(parsed.amount),
        "coins_preview": str(list(parsed.coins)[:10]),
    }
    if extra:
        base.update(extra)
    return base


class CoinChangeVerifier:
    """Coin Change symbolic verifier (DP O(N*A) golden, A <= 1000)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.COIN_CHANGE

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
        if actual != -1 and (actual < 0 or actual > parsed.amount):
            return InvariantViolation(
                invariant_kind="count_in_valid_range",
                description=(
                    f"sample {i}: output={actual} not in [-1] or [0..{parsed.amount}]"
                ),
                evidence=_evidence(parsed, extra={"actual": str(actual)}),
            )
        golden = _dp_min_coins(parsed)
        if golden == -1:
            if actual != -1:
                return InvariantViolation(
                    invariant_kind="existence_consistent_with_dp",
                    description=(
                        f"sample {i}: actual={actual} but DP says impossible"
                    ),
                    evidence=_evidence(parsed, extra={"actual": str(actual)}),
                )
            return None
        if actual == -1:
            return InvariantViolation(
                invariant_kind="existence_consistent_with_dp",
                description=(
                    f"sample {i}: actual=-1 but DP achievable (golden={golden})"
                ),
                evidence=_evidence(parsed, extra={"dp_golden": str(golden)}),
            )
        if actual != golden:
            return InvariantViolation(
                invariant_kind="count_matches_dp_optimal",
                description=f"sample {i}: actual={actual} != dp_golden={golden}",
                evidence=_evidence(
                    parsed,
                    extra={"actual": str(actual), "dp_golden": str(golden)},
                ),
            )
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
