"""Tier sensitivity 측정 실행 (Phase 3 M1 step 4) — 후보를 두 tier 로 판정.

``ipe/v1/nodes/executor.py`` 패턴 미러링: 후보 코드를 sample 입력에 sandbox 실행
→ Tier A(symbolic verifier) + Tier B(differential vs 독립 brute + metamorphic)
판정 → ``TierCase``. ``runner`` 주입 — 단위 테스트는 mock, 실측은 sandbox.

golden + mutants 후보군을 ``measure_algorithm`` 으로 일괄 판정한다. 후보 코드는
fixture(``tier_fixtures``)가 공급 — LLM 0.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schema import AlgorithmDesign, ProblemSpec, SolutionAttempt
from ..verification import classify, run_differential, run_metamorphic, symbolic_axis
from ..verification._exec import CodeRunner, run_code
from ..verifiers import SymbolicVerifier
from .tier_sensitivity import TierCase


@dataclass(frozen=True)
class AlgoFixture:
    """한 알고리즘의 측정 입력 — golden/brute 코드 + spec/design + mutants.

    ``brute`` 는 golden 과 **구조 독립**(naive/exhaustive)이어야 측정이 순환되지
    않는다 (RFC §7.4). ``mutants`` 는 (id, code) — golden 에 버그를 주입한 후보.
    """

    spec: ProblemSpec
    design: AlgorithmDesign
    golden_code: str
    brute_code: str
    mutants: tuple[tuple[str, str], ...]


def _candidate_outputs(
    *, runner: CodeRunner, code: str, inputs: list[str], spec: ProblemSpec
) -> list[str]:
    """후보 코드를 각 입력에 실행 → trim stdout (실패 시 빈 문자열).

    executor ``_to_sample_result`` 와 동일 — OK 아니면 "" (verifier parse-skip).
    """
    outputs: list[str] = []
    for inp in inputs:
        r = run_code(runner, code, inp, spec.time_limit_ms, spec.memory_limit_mb)
        outputs.append(r.stdout.strip() if r.status == "OK" else "")
    return outputs


def measure_candidate(
    *,
    algorithm: str,
    candidate_id: str,
    is_golden: bool,
    candidate_code: str,
    brute_code: str,
    spec: ProblemSpec,
    design: AlgorithmDesign,
    verifier: SymbolicVerifier,
    runner: CodeRunner,
) -> TierCase:
    """한 후보를 Tier A(symbolic) + Tier B(differential+metamorphic)로 판정."""
    inputs = [s.input_text for s in spec.sample_testcases]

    # Tier A — 후보 출력에 symbolic verifier 적용
    outputs = _candidate_outputs(runner=runner, code=candidate_code, inputs=inputs, spec=spec)
    violations = verifier.verify(
        spec=spec,
        design=design,
        attempt=SolutionAttempt(code=candidate_code, iteration=0),
        sample_outputs=outputs,
    )
    sym = symbolic_axis(
        verifier_available=True,
        engaged_samples=verifier.count_engaged_samples(spec),
        violation_count=len(violations),
    )

    # Tier B — 후보 vs 독립 brute 차분 + 범용 metamorphic
    diff = run_differential(
        golden_code=candidate_code,
        brute_code=brute_code,
        inputs=inputs,
        runner=runner,
        time_limit_ms=spec.time_limit_ms,
        memory_limit_mb=spec.memory_limit_mb,
    )
    meta = run_metamorphic(
        code=candidate_code,
        inputs=inputs,
        runner=runner,
        time_limit_ms=spec.time_limit_ms,
        memory_limit_mb=spec.memory_limit_mb,
    )

    verdict = classify(symbolic=sym, differential=diff, metamorphic=meta)
    return TierCase(
        algorithm=algorithm,
        candidate_id=candidate_id,
        is_golden=is_golden,
        tier_a_reached=verdict.tier_a_reached,
        tier_b_reached=verdict.tier_b_reached,
        tier=verdict.tier,
    )


def measure_algorithm(
    *,
    fixture: AlgoFixture,
    verifier: SymbolicVerifier,
    runner: CodeRunner,
) -> list[TierCase]:
    """golden + 모든 mutant 를 판정해 TierCase list 반환."""
    algo = fixture.spec.target_algorithm.value
    cases = [
        measure_candidate(
            algorithm=algo,
            candidate_id="golden",
            is_golden=True,
            candidate_code=fixture.golden_code,
            brute_code=fixture.brute_code,
            spec=fixture.spec,
            design=fixture.design,
            verifier=verifier,
            runner=runner,
        )
    ]
    for mid, code in fixture.mutants:
        cases.append(
            measure_candidate(
                algorithm=algo,
                candidate_id=mid,
                is_golden=False,
                candidate_code=code,
                brute_code=fixture.brute_code,
                spec=fixture.spec,
                design=fixture.design,
                verifier=verifier,
                runner=runner,
            )
        )
    return cases
