"""tier_sensitivity 분석 코어 단위 테스트 (Phase 3 M1 step 4).

순수 집계 — TierCase 를 직접 조립해 4-class confusion matrix 지표를 검증한다.
"""

from __future__ import annotations

from ipe.v1.measurement.tier_sensitivity import (
    AgreementClass,
    TierCase,
    TierSensitivityReport,
    classify_agreement,
)
from ipe.v1.verification import Tier


def _case(
    *,
    cid: str = "c",
    golden: bool = False,
    a: bool,
    b: bool,
    tier: Tier = Tier.C,
) -> TierCase:
    return TierCase(
        algorithm="demo",
        candidate_id=cid,
        is_golden=golden,
        tier_a_reached=a,
        tier_b_reached=b,
        tier=tier,
    )


# --- classify_agreement (4-class) ------------------------------------------


def test_both_accept_is_agree_accept():
    assert (
        classify_agreement(tier_a_reached=True, tier_b_reached=True) is AgreementClass.AGREE_ACCEPT
    )


def test_both_reject_is_agree_reject():
    assert (
        classify_agreement(tier_a_reached=False, tier_b_reached=False)
        is AgreementClass.AGREE_REJECT
    )


def test_tier_a_reject_tier_b_pass_is_tier_b_miss():
    # 위험: symbolic 이 잡은 버그를 Tier B 가 놓침
    assert (
        classify_agreement(tier_a_reached=False, tier_b_reached=True) is AgreementClass.TIER_B_MISS
    )


def test_tier_a_pass_tier_b_reject_is_tier_b_stricter():
    assert (
        classify_agreement(tier_a_reached=True, tier_b_reached=False)
        is AgreementClass.TIER_B_STRICTER
    )


def test_case_agreement_property_delegates():
    assert _case(a=False, b=False).agreement is AgreementClass.AGREE_REJECT


# --- TierSensitivityReport 지표 --------------------------------------------


def test_tier_b_recall_full_when_b_catches_all_a_rejections():
    # Tier A 가 reject 한 2개를 Tier B 도 전부 reject → recall 1.0
    report = TierSensitivityReport(
        cases=(
            _case(cid="golden", golden=True, a=True, b=True, tier=Tier.A),
            _case(cid="m1", a=False, b=False),
            _case(cid="m2", a=False, b=False),
        )
    )
    assert report.tier_b_recall == 1.0
    assert report.tier_b_miss_count == 0
    assert report.tier_a_rejections == 2


def test_tier_b_recall_drops_on_miss():
    # Tier A reject 2개 중 1개를 Tier B 가 놓침 → recall 0.5, miss 1
    report = TierSensitivityReport(
        cases=(
            _case(cid="m1", a=False, b=False),
            _case(cid="m2", a=False, b=True),  # tier_b_miss
        )
    )
    assert report.tier_b_recall == 0.5
    assert report.tier_b_miss_count == 1
    assert report.count(AgreementClass.TIER_B_MISS) == 1


def test_tier_b_recall_none_when_no_tier_a_rejection():
    # Tier A 가 아무것도 reject 안 함 (전부 golden 통과) → recall 정의 불가
    report = TierSensitivityReport(
        cases=(_case(cid="golden", golden=True, a=True, b=True, tier=Tier.A),)
    )
    assert report.tier_b_recall is None
    assert report.tier_a_rejections == 0


def test_tier_b_stricter_counted():
    # Tier A 통과인데 Tier B reject (crash mutant 등) — symbolic 보완
    report = TierSensitivityReport(cases=(_case(cid="m", a=True, b=False),))
    assert report.count(AgreementClass.TIER_B_STRICTER) == 1
    assert report.tier_b_recall is None  # tier_a reject 0


def test_golden_false_rejection_flagged():
    # golden 인데 Tier B 가 reject → precision 문제
    report = TierSensitivityReport(
        cases=(
            _case(cid="golden", golden=True, a=True, b=False, tier=Tier.A),
            _case(cid="m1", a=False, b=False),
        )
    )
    assert report.golden_false_rejections == 1


def test_summary_line_has_key_metrics():
    report = TierSensitivityReport(
        cases=(
            _case(cid="golden", golden=True, a=True, b=True, tier=Tier.A),
            _case(cid="m1", a=False, b=False),
        )
    )
    line = report.summary_line()
    assert "tier_b_recall=100.0%" in line
    assert "tier_b_miss=0" in line
    assert "agree_reject=1" in line
