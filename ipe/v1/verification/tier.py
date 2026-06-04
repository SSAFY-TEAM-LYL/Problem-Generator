"""Tier classifier — symbolic(Tier A) + differential·metamorphic(Tier B) 종합 판정.

RFC §7.2 의 신뢰 tier 게이트를 코드로 구현. 세 검증 축의 결과를 받아 문제가
도달한 신뢰 tier(A/B/C)를 판정하고 B2B 출하 가능 여부를 게이트한다.

- **Tier A**: symbolic(정석 코어의 수학적 정의) 적용 + 통과 → 완전 신뢰.
- **Tier B**: symbolic 불가, 그러나 differential(golden↔brute) + metamorphic(범용
  관계) 둘 다 통과 → hiring-grade 정확성.
- **Tier C**: 위 둘 다 미달 → B2B reject (B2C 강등 or 폐기).

**B2B 게이트** (RFC §7.2): Tier A/B 만 출하, Tier C reject.

설계 결정 — **symbolic 은 authoritative**:
- symbolic 이 위반을 잡으면(FAIL) differential·metamorphic 이 통과해도 **Tier C 로
  강등**한다. 최강 오라클이 오답이라 판정했는데 약한 축의 합의로 출하하면, 바로
  RFC §7.1 의 "상관된 오해"(golden·brute 가 지문을 똑같이 오독)를 출하하는 셈.
- 반대로 symbolic PASS 인데 differential 이 불일치면 **brute 가 버그**(golden 은
  정답) → Tier A 유지. 이 divergence 는 ``tier_b_reached`` 로 노출돼 M1 측정이
  잡는다.

``tier_a_reached`` / ``tier_b_reached`` 는 step 4 측정의 confusion matrix 입력 —
19-algo 에서 두 tier 의 판정이 일치하는지(Tier B ≈ Tier A) 실측한다.

LLM 없음 (deterministic). 입력은 세 검증 모듈의 frozen report — 순수 함수.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .differential import DifferentialReport
from .metamorphic import MetamorphicReport


class Tier(StrEnum):
    """문제가 도달한 신뢰 tier (RFC §7.2)."""

    A = "A"  # symbolic 통과 — 완전 신뢰
    B = "B"  # differential + metamorphic 통과 — hiring-grade
    C = "C"  # 미달 — B2B reject


class TierAxis(StrEnum):
    """한 검증 축의 정규화된 결과.

    ``NO_SIGNAL`` 은 PASS 와 명확히 구분한다 — 신호 없음(축 미적용 / vacuous)을
    통과로 취급하면 검증 안 된 문제가 출하된다 (B2B precision).
    """

    PASS = "pass"  # 축이 실효 신호로 통과
    FAIL = "fail"  # 축이 위반/불일치 검출
    NO_SIGNAL = "no_signal"  # 축 미적용 또는 vacuous (신호 없음)


@dataclass(frozen=True)
class TierVerdict:
    """tier 판정 결과 + 세 축의 정규화 결과 + 판정 근거."""

    tier: Tier
    symbolic: TierAxis
    differential: TierAxis
    metamorphic: TierAxis
    reasons: tuple[str, ...]

    @property
    def shippable_b2b(self) -> bool:
        """RFC §7.2: Tier A/B 만 출하, Tier C reject."""
        return self.tier in (Tier.A, Tier.B)

    @property
    def tier_a_reached(self) -> bool:
        """symbolic 이 실효 통과했는가 (Tier A 증거)."""
        return self.symbolic is TierAxis.PASS

    @property
    def tier_b_reached(self) -> bool:
        """differential + metamorphic 이 둘 다 실효 통과했는가 (Tier B 증거).

        symbolic 과 독립 — step 4 가 ``tier_a_reached`` 와 비교해 Tier B≈Tier A
        confusion matrix 를 만든다.
        """
        return self.differential is TierAxis.PASS and self.metamorphic is TierAxis.PASS


def symbolic_axis(
    *,
    verifier_available: bool,
    engaged_samples: int,
    violation_count: int,
) -> TierAxis:
    """symbolic 검증 결과를 tier 축으로 정규화.

    - ``NO_SIGNAL``: verifier 미등록 또는 engaged sample 0 (symbolic 적용 불가).
    - ``FAIL``: invariant 위반 ≥ 1 (정석 코어가 오답 판정 — 최강 신호).
    - ``PASS``: verifier 적용(engaged ≥ 1) + 위반 0.

    schema 의존을 피하려 ``violation_count`` 만 받는다 —
    ``len(verifier.verify(...))`` 를 넘기면 된다.
    """
    if not verifier_available or engaged_samples <= 0:
        return TierAxis.NO_SIGNAL
    if violation_count > 0:
        return TierAxis.FAIL
    return TierAxis.PASS


def _axis_of(total: int, bad: int) -> TierAxis:
    """(검사 수, 위반 수) → 축. 검사 0 = NO_SIGNAL (vacuous 통과 금지)."""
    if total <= 0:
        return TierAxis.NO_SIGNAL
    if bad > 0:
        return TierAxis.FAIL
    return TierAxis.PASS


def classify(
    *,
    symbolic: TierAxis,
    differential: DifferentialReport | None = None,
    metamorphic: MetamorphicReport | None = None,
) -> TierVerdict:
    """세 검증 축을 종합해 tier 를 판정한다.

    ``symbolic`` 은 ``symbolic_axis(...)`` 로 만든 축. ``differential`` /
    ``metamorphic`` 은 각 모듈의 report (미실행이면 None → NO_SIGNAL).
    """
    diff_axis = (
        _axis_of(differential.total, len(differential.disagreements))
        if differential is not None
        else TierAxis.NO_SIGNAL
    )
    meta_axis = (
        _axis_of(metamorphic.total, len(metamorphic.violations))
        if metamorphic is not None
        else TierAxis.NO_SIGNAL
    )

    reasons = [
        f"symbolic={symbolic.value}",
        f"differential={diff_axis.value}",
        f"metamorphic={meta_axis.value}",
    ]

    if symbolic is TierAxis.PASS:
        tier = Tier.A
        reasons.append("symbolic 통과 → Tier A (완전 신뢰)")
    elif symbolic is TierAxis.FAIL:
        tier = Tier.C
        reasons.append("symbolic 위반 → Tier C (정석 오라클 오답 판정, 출하 불가)")
    elif diff_axis is TierAxis.PASS and meta_axis is TierAxis.PASS:
        tier = Tier.B
        reasons.append("symbolic 불가, differential+metamorphic 통과 → Tier B")
    else:
        tier = Tier.C
        reasons.append("Tier B 미달 (차분/metamorphic 신호 부족) → Tier C (B2B reject)")

    return TierVerdict(
        tier=tier,
        symbolic=symbolic,
        differential=diff_axis,
        metamorphic=meta_axis,
        reasons=tuple(reasons),
    )
