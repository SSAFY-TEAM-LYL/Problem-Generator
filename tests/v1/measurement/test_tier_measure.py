"""tier_measure 측정 실행 테스트 (Phase 3 M1 step 4).

- fast: mock runner + stub verifier 로 measure_candidate/measure_algorithm 배선
  검증 (CI 기본 실행).
- slow: 실제 sandbox 로 two_sum confusion matrix 실증 (``@pytest.mark.slow`` —
  실 subprocess 라 CI 기본 제외, 로컬/slow 스위트에서 RFC §7.5 증거 확인).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.measurement.tier_measure import AlgoFixture, measure_algorithm
from ipe.v1.measurement.tier_sensitivity import AgreementClass, TierSensitivityReport
from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    InvariantViolation,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    TargetAlgorithm,
)

# ---------- fast: mock runner + stub verifier ----------


class _ScriptedRunner:
    """fn(code, stdin) -> (status, stdout) 로 RunResult 생성 (deterministic)."""

    def __init__(self, fn: Callable[[str, str], tuple[str, str]]) -> None:
        self._fn = fn

    def run(self, spec: RunSpec) -> RunResult:
        code = (Path(spec.cwd) / "sol.py").read_text(encoding="utf-8")
        status, stdout = self._fn(code, spec.stdin)
        return RunResult(
            status=status,  # type: ignore[arg-type]
            returncode=0 if status == "OK" else 1,
            stdout=stdout,
            stderr="" if status == "OK" else "boom",
            elapsed_ms=1,
        )


class _StubVerifier:
    """candidate code marker 로 violation 결정 — symbolic 판정 시뮬레이트."""

    target_algorithm = TargetAlgorithm.TWO_SUM

    def verify(
        self,
        spec: ProblemSpec,
        design: AlgorithmDesign,
        attempt: SolutionAttempt,
        sample_outputs: list[str],
    ) -> list[InvariantViolation]:
        if "MUT" in attempt.code:
            return [InvariantViolation(invariant_kind="stub_violation", description="injected bug")]
        return []

    def count_engaged_samples(self, spec: ProblemSpec) -> int:
        return len(spec.sample_testcases)


def _scripted(code: str, stdin: str) -> tuple[str, str]:
    if "MUT_CRASH" in code:
        return ("RTE", "")
    if "MUT_WRONG" in code:
        return ("OK", f"wrong-{stdin}")
    # GOLDEN 과 BRUTE 는 동일 정답 → differential agree, metamorphic pass
    return ("OK", f"ans-{stdin}")


def _stub_fixture() -> AlgoFixture:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="t",
        description="d",
        io_contract=IOContract(input_format="x", output_format="y"),
        sample_testcases=[
            SampleTestCase(input_text="i1", expected_output="ans-i1"),
            SampleTestCase(input_text="i2", expected_output="ans-i2"),
            SampleTestCase(input_text="i3", expected_output="ans-i3"),
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="t",
        complexity_target=ComplexityBound(time_big_o="O(N)", space_big_o="O(1)"),
        pseudocode="p",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code="# GOLDEN",
        brute_code="# BRUTE",
        mutants=(("mut-wrong", "# MUT_WRONG"), ("mut-crash", "# MUT_CRASH")),
    )


def test_golden_reaches_both_tiers_with_stub():
    cases = measure_algorithm(
        fixture=_stub_fixture(),
        verifier=_StubVerifier(),
        runner=_ScriptedRunner(_scripted),
    )
    golden = next(c for c in cases if c.is_golden)
    assert golden.tier_a_reached is True  # stub verify → no violation
    assert golden.tier_b_reached is True  # diff agree + meta pass
    assert golden.agreement is AgreementClass.AGREE_ACCEPT


def test_wrong_mutant_rejected_by_both_tiers():
    cases = measure_algorithm(
        fixture=_stub_fixture(),
        verifier=_StubVerifier(),
        runner=_ScriptedRunner(_scripted),
    )
    mut = next(c for c in cases if c.candidate_id == "mut-wrong")
    assert mut.tier_a_reached is False  # stub violation
    assert mut.tier_b_reached is False  # differential disagree
    assert mut.agreement is AgreementClass.AGREE_REJECT


def test_crash_mutant_caught_by_metamorphic():
    cases = measure_algorithm(
        fixture=_stub_fixture(),
        verifier=_StubVerifier(),
        runner=_ScriptedRunner(_scripted),
    )
    mut = next(c for c in cases if c.candidate_id == "mut-crash")
    assert mut.tier_b_reached is False  # metamorphic well_formed fails on RTE


def test_report_aggregates_stub_cases():
    cases = measure_algorithm(
        fixture=_stub_fixture(),
        verifier=_StubVerifier(),
        runner=_ScriptedRunner(_scripted),
    )
    rep = TierSensitivityReport(cases=tuple(cases))
    assert rep.total == 3
    assert rep.tier_b_miss_count == 0
    assert rep.golden_false_rejections == 0


# ---------- slow: 실제 sandbox 로 two_sum 실증 ----------


@pytest.mark.slow
def test_two_sum_real_sandbox_tier_b_matches_tier_a():
    """RFC §7.5 증거: two_sum golden+mutants 에서 Tier B 가 Tier A 와 일치.

    실 subprocess sandbox — CI 기본(``not slow``)에서 제외, 로컬 검증용.
    """
    from ipe.sandbox.selector import pick_runner
    from ipe.v1.measurement.tier_fixtures import two_sum_fixture
    from ipe.v1.verifiers import get_verifier

    verifier = get_verifier(TargetAlgorithm.TWO_SUM)
    assert verifier is not None
    cases = measure_algorithm(fixture=two_sum_fixture(), verifier=verifier, runner=pick_runner())
    rep = TierSensitivityReport(cases=tuple(cases))
    # golden 은 두 tier 통과, 모든 mutant 은 두 tier 가 함께 reject
    assert rep.golden_false_rejections == 0
    assert rep.tier_b_miss_count == 0
    assert rep.tier_b_recall == 1.0
