"""LIS (Longest Increasing Subsequence) symbolic verifier — D안 Phase 2a PR-B1.

Invariants (3):
1. ``non_negative_length``: 출력 LIS 길이 >= 0.
2. ``length_le_input_size``: 출력 길이 <= 입력 sequence 길이 N.
3. ``length_optimal``: patience sort O(N log N) golden 과 일치 (strictly
   increasing LIS).

Input format (Phase 2a 단순화)::

    N
    a_1 a_2 ... a_N

Output format (Phase 2a 단순화): 단일 정수 — strictly increasing LIS 길이.

format mismatch / parse 실패 시 verifier silent skip — executor 의 sample exact
match 로 fallback. Phase 3 에서 IOContract 기반 generic parser 검토.

**Strictly increasing 채택 이유**: non-decreasing variant 보다 더 좁은 정답이라
verifier 강도 ↑. baseline 5 algo 비교 시 LLM 이 strict/non-strict 헷갈리면
SAMPLE_MISMATCH 로 잡힘.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

from ..schema import (
    AlgorithmDesign,
    InvariantViolation,
    ProblemSpec,
    SolutionAttempt,
    TargetAlgorithm,
)


@dataclass(frozen=True)
class _ParsedSequence:
    """parsed sample input → 정수 시퀀스."""

    n: int
    arr: tuple[int, ...]


def _parse_sample_input(text: str) -> _ParsedSequence | None:
    """``N`` + ``a_1 ... a_N`` 형식 parse. 실패 시 None (verifier skip).

    Empty arr (N=0) 도 허용. ``a_1 ...`` 줄이 없으면 (N=0 일 때만) OK.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None
    try:
        n = int(lines[0])
    except ValueError:
        return None
    if n < 0:
        return None
    if n == 0:
        return _ParsedSequence(n=0, arr=())
    if len(lines) < 2:
        return None
    try:
        values = tuple(int(x) for x in lines[1].split())
    except ValueError:
        return None
    if len(values) != n:
        return None
    return _ParsedSequence(n=n, arr=values)


def _lis_length_patience_sort(arr: tuple[int, ...]) -> int:
    """O(N log N) patience sort 로 strictly increasing LIS 길이 산출.

    Dijkstra 의 Bellman-Ford golden 과 같은 역할 — algorithm 자체 (DP) 와 다른
    접근으로 self-cross-check.
    """
    tails: list[int] = []
    for x in arr:
        i = bisect_left(tails, x)
        if i == len(tails):
            tails.append(x)
        else:
            tails[i] = x
    return len(tails)


def _evidence(seq: _ParsedSequence, actual: int) -> dict[str, str]:
    arr_preview = " ".join(str(x) for x in seq.arr[:10])
    if seq.n > 10:
        arr_preview += " ..."
    return {
        "N": str(seq.n),
        "arr_preview": arr_preview,
        "actual_output": str(actual),
    }


class LISVerifier:
    """LIS-specific symbolic verifier.

    각 sample 마다 parse → 3 invariants. 위반 시 short-circuit (Dijkstra 패턴
    동일).
    """

    target_algorithm: TargetAlgorithm = TargetAlgorithm.LIS

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
            seq = _parse_sample_input(sample.input_text)
            if seq is None:
                continue
            try:
                actual = int(output_str.strip())
            except (ValueError, AttributeError):
                continue
            sample_violation = self._check_sample(i, seq, actual)
            if sample_violation is not None:
                violations.append(sample_violation)
        return violations

    def _check_sample(
        self, i: int, seq: _ParsedSequence, actual: int
    ) -> InvariantViolation | None:
        if actual < 0:
            return InvariantViolation(
                invariant_kind="non_negative_length",
                description=f"sample {i}: actual={actual} < 0 (LIS 길이 음수 불가)",
                evidence=_evidence(seq, actual),
            )
        if actual > seq.n:
            return InvariantViolation(
                invariant_kind="length_le_input_size",
                description=(
                    f"sample {i}: actual={actual} > N={seq.n} "
                    "(LIS 길이가 입력 크기 초과 불가)"
                ),
                evidence=_evidence(seq, actual),
            )
        golden = _lis_length_patience_sort(seq.arr)
        if actual != golden:
            return InvariantViolation(
                invariant_kind="length_optimal",
                description=(
                    f"sample {i}: actual={actual} != patience-sort golden={golden}"
                ),
                evidence={
                    **_evidence(seq, actual),
                    "patience_sort_golden": str(golden),
                },
            )
        return None

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        """parse 가능한 sample 수 — H1 측정의 verifier 실효성 신호."""
        return sum(
            1
            for sample in spec.sample_testcases
            if _parse_sample_input(sample.input_text) is not None
        )
