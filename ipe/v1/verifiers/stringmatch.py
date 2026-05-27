"""String Match symbolic verifier — D안 Phase 2b PR-C6.

variant: **classic substring search — first occurrence**. ``text`` 안에서
``pattern`` 의 첫 번째 1-indexed 출현 index. 없으면 -1. Single pattern only.

Cluster verifier (PR-C5 pattern): KMP / Z-algorithm / Rabin-Karp / Aho-Corasick
single-pattern family 모두 cover (verifier 는 결과만 봄, algorithm 선택은
designer 자유).

Invariants (4):
1. ``output_is_single_int``: 단일 정수.
2. ``index_valid_range``: -1 또는 1 <= idx <= len(text) - len(pattern) + 1.
3. ``text_at_index_matches_pattern``: idx > 0 일 때
   ``text[idx-1 : idx-1+len(pattern)] == pattern``.
4. ``existence_consistent``: brute O(NM) golden 발견여부와 일치.

Input format::

    text
    pattern

(2 lines, 각 line non-empty, ASCII printable — whitespace 금지)

Output: 단일 정수 — 1-indexed first occurrence index, 또는 ``-1``.
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
    text: str
    pattern: str


def _parse_sample_input(text: str) -> _ParsedInput | None:
    lines = text.split("\n")
    non_empty = [line for line in lines if line != ""]
    if len(non_empty) != 2:
        return None
    text_line, pattern_line = non_empty[0], non_empty[1]
    if pattern_line == "":
        return None
    if any(c.isspace() for c in text_line) or any(
        c.isspace() for c in pattern_line
    ):
        return None
    return _ParsedInput(text=text_line, pattern=pattern_line)


def _brute_first_occurrence(parsed: _ParsedInput) -> int:
    n = len(parsed.text)
    m = len(parsed.pattern)
    if m == 0:
        return -1
    for i in range(n - m + 1):
        if parsed.text[i : i + m] == parsed.pattern:
            return i + 1
    return -1


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
        "text_len": str(len(parsed.text)),
        "pattern_len": str(len(parsed.pattern)),
        "pattern": parsed.pattern[:30],
    }
    if extra:
        base.update(extra)
    return base


class StringMatchVerifier:
    """String Match symbolic verifier (first occurrence, brute O(NM) golden)."""

    target_algorithm: TargetAlgorithm = TargetAlgorithm.STRING_MATCH

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
        n = len(parsed.text)
        m = len(parsed.pattern)
        max_idx = n - m + 1
        if actual != -1 and not (1 <= actual <= max_idx):
            return InvariantViolation(
                invariant_kind="index_valid_range",
                description=(
                    f"sample {i}: output={actual} not in [-1] or [1..{max_idx}]"
                ),
                evidence=_evidence(parsed, extra={"actual": str(actual)}),
            )
        if actual > 0:
            window = parsed.text[actual - 1 : actual - 1 + m]
            if window != parsed.pattern:
                return InvariantViolation(
                    invariant_kind="text_at_index_matches_pattern",
                    description=(
                        f"sample {i}: text[{actual - 1}:{actual - 1 + m}]="
                        f"{window!r} != pattern={parsed.pattern!r}"
                    ),
                    evidence=_evidence(
                        parsed,
                        extra={"actual": str(actual), "window": window[:30]},
                    ),
                )
        brute = _brute_first_occurrence(parsed)
        actual_found = actual > 0
        brute_found = brute > 0
        if actual_found != brute_found:
            return InvariantViolation(
                invariant_kind="existence_consistent",
                description=(
                    f"sample {i}: output={actual} (found={actual_found}) inconsistent "
                    f"with brute={brute} (found={brute_found})"
                ),
                evidence=_evidence(
                    parsed,
                    extra={"actual": str(actual), "brute": str(brute)},
                ),
            )
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
