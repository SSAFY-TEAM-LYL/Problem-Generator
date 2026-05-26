"""Two Sum symbolic verifier — D안 Phase 2a PR-B3.

Invariants (4):
1. ``output_format_valid``: 출력이 ``-1`` 단독 또는 ``i j`` (두 정수) 형식.
2. ``indices_in_range_and_ordered``: ``i j`` 출력 시 1 <= i < j <= N.
3. ``sum_equals_target``: ``i j`` 출력 시 a[i] + a[j] == T.
4. ``existence_consistent``: brute O(N²) golden 으로 검증 — 해가 존재하면 LLM
   이 valid pair (또는 valid 한 그 어느 쌍) 출력해야 하고, 해가 없으면 ``-1``.

Input format (Phase 2a 단순화 — competitive programming 표준 1-indexed)::

    N T
    a_1 a_2 ... a_N

Output format: ``i j`` (1-indexed, i < j) 또는 ``-1`` (no valid pair).

format mismatch / parse 실패 시 verifier silent skip — executor sample exact
match fallback (PR-B2.1 패턴 동일).
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
    target: int
    arr: tuple[int, ...]


def _parse_sample_input(text: str) -> _ParsedInput | None:
    """``N T`` 첫 줄 + array 둘째 줄 parse. 실패 시 None."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    first = lines[0].split()
    if len(first) != 2:
        return None
    try:
        n = int(first[0])
        target = int(first[1])
    except ValueError:
        return None
    if n <= 0:
        return None
    try:
        values = tuple(int(x) for x in lines[1].split())
    except ValueError:
        return None
    if len(values) != n:
        return None
    return _ParsedInput(n=n, target=target, arr=values)


def _parse_output(text: str) -> tuple[int, int] | str | None:
    """Parse output: ``-1`` → "none", ``i j`` → (i, j), else None.

    Returns:
        - ``"none"`` if output is ``-1``.
        - ``(i, j)`` tuple of 1-indexed integers.
        - ``None`` if unparseable.
    """
    stripped = text.strip()
    if stripped == "-1":
        return "none"
    parts = stripped.split()
    if len(parts) != 2:
        return None
    try:
        i = int(parts[0])
        j = int(parts[1])
    except ValueError:
        return None
    return (i, j)


def _find_any_brute_pair(arr: tuple[int, ...], target: int) -> tuple[int, int] | None:
    """brute O(N²) 검증 — 1-indexed (i, j) with i < j and a[i]+a[j]==target.

    return: first valid pair (lex order) 또는 None (no pair).
    """
    n = len(arr)
    for i in range(n):
        for j in range(i + 1, n):
            if arr[i] + arr[j] == target:
                return (i + 1, j + 1)
    return None


def _evidence(
    parsed: _ParsedInput, actual: str, *, extra: dict[str, str] | None = None
) -> dict[str, str]:
    arr_preview = " ".join(str(x) for x in parsed.arr[:10])
    if parsed.n > 10:
        arr_preview += " ..."
    base = {
        "N": str(parsed.n),
        "T": str(parsed.target),
        "arr_preview": arr_preview,
        "actual_output": actual.strip(),
    }
    if extra:
        base.update(extra)
    return base


class TwoSumVerifier:
    """Two Sum specific symbolic verifier (1-indexed, i<j, brute golden)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.TWO_SUM

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
            parsed_output = _parse_output(output_str)
            if parsed_output is None:
                violations.append(
                    InvariantViolation(
                        invariant_kind="output_format_valid",
                        description=(
                            f"sample {i}: output {output_str.strip()!r} is "
                            "not '-1' or 'i j' (two integers)"
                        ),
                        evidence=_evidence(parsed, output_str),
                    )
                )
                continue
            sample_violation = self._check_sample(i, parsed, output_str, parsed_output)
            if sample_violation is not None:
                violations.append(sample_violation)
        return violations

    def _check_sample(
        self,
        i: int,
        parsed: _ParsedInput,
        raw_output: str,
        parsed_output: tuple[int, int] | str,
    ) -> InvariantViolation | None:
        brute = _find_any_brute_pair(parsed.arr, parsed.target)
        # case: LLM says "no pair" (-1)
        if parsed_output == "none":
            if brute is not None:
                return InvariantViolation(
                    invariant_kind="existence_consistent",
                    description=(
                        f"sample {i}: actual='-1' (no pair) but brute found "
                        f"pair {brute}"
                    ),
                    evidence=_evidence(
                        parsed, raw_output, extra={"brute_pair": str(brute)}
                    ),
                )
            return None
        # case: LLM says (i, j) pair
        assert isinstance(parsed_output, tuple)
        a, b = parsed_output
        if not (1 <= a < b <= parsed.n):
            return InvariantViolation(
                invariant_kind="indices_in_range_and_ordered",
                description=(
                    f"sample {i}: ({a}, {b}) violates 1<=i<j<=N (N={parsed.n})"
                ),
                evidence=_evidence(parsed, raw_output),
            )
        # arr is 0-indexed internally, but parsed_output is 1-indexed
        actual_sum = parsed.arr[a - 1] + parsed.arr[b - 1]
        if actual_sum != parsed.target:
            return InvariantViolation(
                invariant_kind="sum_equals_target",
                description=(
                    f"sample {i}: a[{a}]+a[{b}] = "
                    f"{parsed.arr[a - 1]}+{parsed.arr[b - 1]} = {actual_sum} "
                    f"!= T={parsed.target}"
                ),
                evidence=_evidence(
                    parsed,
                    raw_output,
                    extra={
                        "a_i": str(parsed.arr[a - 1]),
                        "a_j": str(parsed.arr[b - 1]),
                    },
                ),
            )
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        """parse 가능한 sample 수 — H1 측정 verifier 실효성 신호."""
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
