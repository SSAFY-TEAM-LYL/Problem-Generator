"""tier classifier 단위 테스트 (Phase 3 M1, step 3).

순수 함수 — runner 불필요. DifferentialReport / MetamorphicReport 를 직접
조립해 세 검증 축의 조합별 tier 판정과 B2B 게이트를 검증한다.
"""

from __future__ import annotations

from ipe.v1.verification import (
    DifferentialCase,
    DifferentialReport,
    MetamorphicReport,
    MetamorphicResult,
    Tier,
    TierAxis,
    classify,
    symbolic_axis,
)


def _diff(*, agreed: bool, n: int = 2) -> DifferentialReport:
    """n 개 케이스가 전부 일치(agreed=True) 또는 전부 불일치인 report."""
    cases = tuple(
        DifferentialCase(
            input_text=str(i),
            golden_output="x",
            brute_output="x" if agreed else "y",
            golden_status="OK",
            brute_status="OK",
            agreed=agreed,
        )
        for i in range(n)
    )
    return DifferentialReport(cases=cases)


def _meta(*, passed: bool, n: int = 2) -> MetamorphicReport:
    results = tuple(
        MetamorphicResult(relation="well_formed", input_text=str(i), passed=passed, detail="")
        for i in range(n)
    )
    return MetamorphicReport(results=results)


# --- symbolic_axis 정규화 ---------------------------------------------------


def test_symbolic_axis_no_verifier_is_no_signal():
    axis = symbolic_axis(verifier_available=False, engaged_samples=3, violation_count=0)
    assert axis is TierAxis.NO_SIGNAL


def test_symbolic_axis_zero_engaged_is_no_signal():
    # verifier 는 있지만 parse 가능한 sample 0 → symbolic 실효 신호 없음
    axis = symbolic_axis(verifier_available=True, engaged_samples=0, violation_count=0)
    assert axis is TierAxis.NO_SIGNAL


def test_symbolic_axis_violation_is_fail():
    axis = symbolic_axis(verifier_available=True, engaged_samples=2, violation_count=1)
    assert axis is TierAxis.FAIL


def test_symbolic_axis_clean_is_pass():
    axis = symbolic_axis(verifier_available=True, engaged_samples=2, violation_count=0)
    assert axis is TierAxis.PASS


# --- tier 판정 --------------------------------------------------------------


def test_symbolic_pass_is_tier_a_shippable():
    v = classify(
        symbolic=TierAxis.PASS,
        differential=_diff(agreed=True),
        metamorphic=_meta(passed=True),
    )
    assert v.tier is Tier.A
    assert v.shippable_b2b is True
    assert v.tier_a_reached is True


def test_symbolic_fail_forces_tier_c_even_if_diff_meta_pass():
    # 최강 오라클(symbolic)이 오답 판정 → diff+meta 통과해도 출하 불가.
    v = classify(
        symbolic=TierAxis.FAIL,
        differential=_diff(agreed=True),
        metamorphic=_meta(passed=True),
    )
    assert v.tier is Tier.C
    assert v.shippable_b2b is False
    # 측정 관점: Tier A 미도달이지만 Tier B 는 도달 (= 상관오해 위험 케이스)
    assert v.tier_a_reached is False
    assert v.tier_b_reached is True


def test_no_symbolic_with_diff_and_meta_pass_is_tier_b():
    v = classify(
        symbolic=TierAxis.NO_SIGNAL,
        differential=_diff(agreed=True),
        metamorphic=_meta(passed=True),
    )
    assert v.tier is Tier.B
    assert v.shippable_b2b is True
    assert v.tier_b_reached is True


def test_no_symbolic_with_differential_fail_is_tier_c():
    v = classify(
        symbolic=TierAxis.NO_SIGNAL,
        differential=_diff(agreed=False),
        metamorphic=_meta(passed=True),
    )
    assert v.tier is Tier.C
    assert v.shippable_b2b is False
    assert v.tier_b_reached is False


def test_no_symbolic_with_metamorphic_fail_is_tier_c():
    v = classify(
        symbolic=TierAxis.NO_SIGNAL,
        differential=_diff(agreed=True),
        metamorphic=_meta(passed=False),
    )
    assert v.tier is Tier.C
    assert v.tier_b_reached is False


def test_no_signals_at_all_is_tier_c():
    # symbolic 불가 + differential/metamorphic 미실행(None) → 신호 없음 → reject
    v = classify(symbolic=TierAxis.NO_SIGNAL)
    assert v.tier is Tier.C
    assert v.shippable_b2b is False
    assert v.differential is TierAxis.NO_SIGNAL
    assert v.metamorphic is TierAxis.NO_SIGNAL


def test_empty_differential_report_is_no_signal_not_pass():
    # 입력 0개 = vacuous → NO_SIGNAL (PASS 아님). Tier B 미달.
    v = classify(
        symbolic=TierAxis.NO_SIGNAL,
        differential=DifferentialReport(cases=()),
        metamorphic=_meta(passed=True),
    )
    assert v.differential is TierAxis.NO_SIGNAL
    assert v.tier is Tier.C


# --- 측정용 divergence (Tier B ≈ Tier A 의 confusion matrix 입력) -----------


def test_tier_a_reached_but_not_tier_b_is_surfaced():
    # symbolic PASS 인데 brute 가 버그라 differential FAIL → Tier B 가 정답을 reject.
    v = classify(
        symbolic=TierAxis.PASS,
        differential=_diff(agreed=False),
        metamorphic=_meta(passed=True),
    )
    assert v.tier is Tier.A  # symbolic 이 authoritative → 출하 가능
    assert v.tier_a_reached is True
    assert v.tier_b_reached is False  # 측정에서 divergence 로 잡힘


def test_both_tiers_reached_is_the_agreement_case():
    v = classify(
        symbolic=TierAxis.PASS,
        differential=_diff(agreed=True),
        metamorphic=_meta(passed=True),
    )
    assert v.tier_a_reached is True
    assert v.tier_b_reached is True  # 두 tier 일치 = M1 이 원하는 결과


def test_reasons_are_populated_for_observability():
    v = classify(symbolic=TierAxis.PASS)
    assert any("Tier A" in r for r in v.reasons)
    assert any("symbolic" in r for r in v.reasons)
