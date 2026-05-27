"""Binary Search symbolic verifier — D안 Phase 2b PR-C1.

variant: **classic** — 정확히 일치하는 1-indexed 위치 반환, 못 찾으면 ``-1``.
lower_bound / upper_bound / count-of-target 등 variant 는 Phase 3.

Invariants (4):
1. ``output_format_valid``: 출력이 단일 정수 (-1 또는 positive).
2. ``index_in_range``: 출력이 ``-1`` 또는 1 <= idx <= N.
3. ``value_matches_target_when_found``: idx > 0 일 때 ``a[idx] == T``.
4. ``existence_consistent``: linear scan golden 의 발견 여부와 일치.

Input format (1-indexed, sorted ascending)::

    N T
    a_1 a_2 ... a_N

Output: 1-indexed index 또는 ``-1`` (no match). 여러 valid index 시 어느 하나
OK.
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


def _linear_scan_indices(arr: tuple[int, ...], target: int) -> tuple[int, ...]:
    return tuple(i + 1 for i, x in enumerate(arr) if x == target)


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


class BinarySearchVerifier:
    """Binary Search (classic) specific symbolic verifier."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.BINARY_SEARCH

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
            try:
                actual = int(output_str.strip())
            except (ValueError, AttributeError):
                violations.append(
                    InvariantViolation(
                        invariant_kind="output_format_valid",
                        description=(
                            f"sample {i}: output {output_str.strip()!r} is not "
                            "a single integer"
                        ),
                        evidence=_evidence(parsed, output_str),
                    )
                )
                continue
            sample_violation = self._check_sample(i, parsed, output_str, actual)
            if sample_violation is not None:
                violations.append(sample_violation)
        return violations

    def _check_sample(
        self,
        i: int,
        parsed: _ParsedInput,
        raw_output: str,
        actual: int,
    ) -> InvariantViolation | None:
        golden_indices = _linear_scan_indices(parsed.arr, parsed.target)
        if actual == -1:
            if golden_indices:
                return InvariantViolation(
                    invariant_kind="existence_consistent",
                    description=(
                        f"sample {i}: actual=-1 but target={parsed.target} "
                        f"exists at positions {list(golden_indices)}"
                    ),
                    evidence=_evidence(
                        parsed,
                        raw_output,
                        extra={"golden_positions": str(list(golden_indices))},
                    ),
                )
            return None
        if actual <= 0:
            return InvariantViolation(
                invariant_kind="output_format_valid",
                description=(
                    f"sample {i}: actual={actual} — must be -1 or positive index"
                ),
                evidence=_evidence(parsed, raw_output),
            )
        if not (1 <= actual <= parsed.n):
            return InvariantViolation(
                invariant_kind="index_in_range",
                description=(
                    f"sample {i}: idx={actual} violates 1<=idx<=N (N={parsed.n})"
                ),
                evidence=_evidence(parsed, raw_output),
            )
        if parsed.arr[actual - 1] != parsed.target:
            return InvariantViolation(
                invariant_kind="value_matches_target_when_found",
                description=(
                    f"sample {i}: a[{actual}]={parsed.arr[actual - 1]} != "
                    f"T={parsed.target}"
                ),
                evidence=_evidence(
                    parsed,
                    raw_output,
                    extra={"value_at_idx": str(parsed.arr[actual - 1])},
                ),
            )
        if not golden_indices:
            return InvariantViolation(
                invariant_kind="existence_consistent",
                description=(
                    f"sample {i}: actual={actual} but target={parsed.target} "
                    "absent (linear scan)"
                ),
                evidence=_evidence(parsed, raw_output),
            )
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
