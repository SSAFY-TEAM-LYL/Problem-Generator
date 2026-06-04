"""Tier sensitivity 분석 (Phase 3 M1 step 4) — Tier A ↔ Tier B confusion matrix.

RFC §7.5: symbolic(Tier A)가 존재하는 19-algo 구간에서 differential+metamorphic
(Tier B)가 Tier A와 일치하는가? 일치하면 symbolic 부재 구간에 Tier B를 신뢰할
권리를 측정으로 획득한다. golden + mutants 후보를 두 tier로 판정해 4-class
confusion matrix로 집계한다.

핵심 신호:
- ``tier_b_miss``: Tier A가 reject 했는데 Tier B가 통과 → **위험** (Tier B가
  symbolic이 잡은 버그를 놓침). 이 비율이 0에 가까워야 Tier B 신뢰 가능.
- ``agree_reject``: 둘 다 reject — Tier B가 Tier A와 함께 버그를 잡음.
- ``tier_b_stricter``: Tier A는 통과, Tier B는 reject — Tier B가 symbolic이 놓친
  버그를 추가로 잡음(crash/nondeterminism 등). symbolic 보완 신호.

순수 분석 — 코드 실행은 ``tier_measure``가, 본 모듈은 판정 결과 집계만 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..verification import Tier


class AgreementClass(StrEnum):
    """한 후보에 대한 Tier A vs Tier B 판정 일치 분류."""

    AGREE_ACCEPT = "agree_accept"  # 둘 다 통과 (정답을 정답으로)
    AGREE_REJECT = "agree_reject"  # 둘 다 reject (Tier B가 Tier A와 함께 잡음)
    TIER_B_MISS = "tier_b_miss"  # Tier A reject, Tier B 통과 (위험 — Tier B가 놓침)
    TIER_B_STRICTER = "tier_b_stricter"  # Tier A 통과, Tier B reject (Tier B가 더 잡음)


def classify_agreement(*, tier_a_reached: bool, tier_b_reached: bool) -> AgreementClass:
    """두 tier 의 도달 여부 → 4-class 일치 분류."""
    if tier_a_reached and tier_b_reached:
        return AgreementClass.AGREE_ACCEPT
    if not tier_a_reached and not tier_b_reached:
        return AgreementClass.AGREE_REJECT
    if not tier_a_reached and tier_b_reached:
        return AgreementClass.TIER_B_MISS
    return AgreementClass.TIER_B_STRICTER


@dataclass(frozen=True)
class TierCase:
    """한 후보(golden 또는 mutant)의 두 tier 판정 결과."""

    algorithm: str
    candidate_id: str  # "golden" | "mut-<n>"
    is_golden: bool
    tier_a_reached: bool
    tier_b_reached: bool
    tier: Tier  # classify() 최종 tier (A/B/C)

    @property
    def agreement(self) -> AgreementClass:
        return classify_agreement(
            tier_a_reached=self.tier_a_reached, tier_b_reached=self.tier_b_reached
        )


@dataclass(frozen=True)
class TierSensitivityReport:
    """후보 case 집계 — RFC §7.5 의 Tier B≈Tier A 판정 지표."""

    cases: tuple[TierCase, ...]

    @property
    def total(self) -> int:
        return len(self.cases)

    def count(self, cls: AgreementClass) -> int:
        return sum(1 for c in self.cases if c.agreement is cls)

    @property
    def tier_a_rejections(self) -> int:
        """Tier A(symbolic)가 reject 한 후보 수 — tier_b_recall 의 분모."""
        return sum(1 for c in self.cases if not c.tier_a_reached)

    @property
    def tier_b_miss_count(self) -> int:
        """Tier A는 잡았는데 Tier B가 놓친 수 (위험 — 0 이어야 신뢰)."""
        return self.count(AgreementClass.TIER_B_MISS)

    @property
    def tier_b_recall(self) -> float | None:
        """Tier A가 잡은 것 중 Tier B도 잡은 비율. Tier A reject 0 이면 None.

        ``1.0`` 이면 Tier B가 symbolic이 잡은 버그를 전부 잡음 → RFC §7.5 충족
        (symbolic 부재 구간에 Tier B 신뢰 획득). ``< 1.0`` 이면 ``tier_b_miss``
        존재 = 상한을 symbolic-only 로 낮추는 rollback trigger 후보.
        """
        denom = self.tier_a_rejections
        if denom == 0:
            return None
        return self.count(AgreementClass.AGREE_REJECT) / denom

    @property
    def golden_false_rejections(self) -> int:
        """golden(정답)인데 Tier B가 reject 한 수 — Tier B false-positive 가드.

        > 0 이면 brute 가 버그거나 metamorphic 이 과엄격 = Tier B precision 문제.
        """
        return sum(1 for c in self.cases if c.is_golden and not c.tier_b_reached)

    def summary_line(self) -> str:
        """한 줄 요약 — 측정 출력용."""
        recall = self.tier_b_recall
        recall_s = "n/a" if recall is None else f"{recall * 100:.1f}%"
        return (
            f"cases={self.total} "
            f"agree_accept={self.count(AgreementClass.AGREE_ACCEPT)} "
            f"agree_reject={self.count(AgreementClass.AGREE_REJECT)} "
            f"tier_b_miss={self.tier_b_miss_count} "
            f"tier_b_stricter={self.count(AgreementClass.TIER_B_STRICTER)} "
            f"tier_b_recall={recall_s} "
            f"golden_false_rej={self.golden_false_rejections}"
        )
