"""full mode 그래프 통합테스트 (Phase 3 M2 step4) — compat flag mode='full'.

mock architect/designer/golden/brute LLM + scripted runner 로 병렬 synthesis
end-to-end 검증:
1. success: golden×2 일치 + brute 일치 → reconcile 채택 → bridge → executor pass
   → end_success. candidates 가 dedup reducer 로 fan-out 폭(3)에 고정(중복 없음).
2. synthesis rejected: golden 불일치 → end_synthesis_rejected (fail_synthesis_rejected).
3. verification fail: synthesis 채택됐으나 canonical 이 sample mismatch →
   end_verification_fail (fail_verification, single-shot — fix loop 없음).
4. canonical mode (기본) 무영향: mode='canonical' 은 기존 linear 경로.
5. mode='full' golden_llms 누락 → build 거부.

reconciler(sol.py) 와 executor(solution.py) 가 같은 주입 runner 를 공유하므로
mock 은 cwd 의 .py 파일을 이름 무관하게 읽는다.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.graph import build_graph
from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    Invariant,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    TargetAlgorithm,
)
from ipe.v1.state import V1State, initial_state

_INPUTS = ["i1", "i2", "i3"]


def _spec(expected_prefix: str = "ans") -> ProblemSpec:
    """expected_output = f'{prefix}-{input}'. prefix='ans' 면 정답 runner 와 일치."""
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="t",
        description="d",
        io_contract=IOContract(input_format="i", output_format="o"),
        sample_testcases=[
            SampleTestCase(input_text=i, expected_output=f"{expected_prefix}-{i}")
            for i in _INPUTS
        ],
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="two_sum",
        complexity_target=ComplexityBound(time_big_o="O(n)", space_big_o="O(n)"),
        pseudocode="hash map.",
        invariants=[Invariant(kind="unique_pair", description="x")],
    )


class _FixedArchitectLLM:
    def __init__(self, spec: ProblemSpec) -> None:
        self._spec = spec

    def generate(self, state: V1State) -> ProblemSpec:
        return self._spec


class _FixedDesignerLLM:
    def __init__(self, design: AlgorithmDesign) -> None:
        self._design = design

    def generate(self, state: V1State) -> AlgorithmDesign:
        return self._design


class _FixedCoderLLM:
    def __init__(self, code: str) -> None:
        self._code = code

    def generate(self, state: V1State) -> SolutionAttempt:
        return SolutionAttempt(code=self._code, iteration=0)


class _MarkerRunner:
    """cwd 의 .py 파일(sol.py/solution.py 무관)을 읽어 marker 로 출력 결정."""

    def __init__(self, fn: Callable[[str, str], tuple[str, str]]) -> None:
        self._fn = fn

    def run(self, spec: RunSpec) -> RunResult:
        py_files = sorted(Path(spec.cwd).glob("*.py"))
        code = py_files[0].read_text(encoding="utf-8") if py_files else ""
        status, stdout = self._fn(code, spec.stdin)
        return RunResult(
            status=status,  # type: ignore[arg-type]
            returncode=0 if status == "OK" else 1,
            stdout=stdout,
            stderr="" if status == "OK" else "boom",
            elapsed_ms=1,
        )


def _by_marker(code: str, stdin: str) -> tuple[str, str]:
    if "CRASH" in code:
        return ("RTE", "")
    if "WRONG" in code:
        return ("OK", f"wrong-{stdin}")
    return ("OK", f"ans-{stdin}")


def _no_verifier(_algo: TargetAlgorithm) -> None:
    """verifier 미사용 — executor 가 sample 비교만 (full mode 검증 isolation)."""
    return None


def _final(raw: Any) -> V1State:
    if isinstance(raw, V1State):
        return raw
    return V1State.model_validate(raw)


def _full_graph(
    *,
    spec: ProblemSpec,
    golden_codes: list[str],
    brute_code: str = "# B",
    golden_origins: list[str] | None = None,
) -> Any:
    return build_graph(
        mode="full",
        architect_llm=_FixedArchitectLLM(spec),
        designer_llm=_FixedDesignerLLM(_design()),
        golden_llms=[_FixedCoderLLM(c) for c in golden_codes],
        brute_llm=_FixedCoderLLM(brute_code),
        golden_origins=golden_origins,
        runner=_MarkerRunner(_by_marker),
        verifier_getter=_no_verifier,
    )


# ---------- 1. full mode success ----------


def test_full_mode_success_adopts_canonical_and_verifies() -> None:
    graph = _full_graph(
        spec=_spec("ans"),
        golden_codes=["# G0", "# G1"],
        golden_origins=["opus", "sonnet"],
    )
    final = _final(graph.invoke(initial_state("run-full-ok", TargetAlgorithm.TWO_SUM)))

    assert final.final_status == "success"
    assert final.reconciliation is not None
    assert final.reconciliation.all_agree is True
    assert final.reconciliation.adopted_origin == "opus"  # fanout_index 0
    assert final.attempt is not None
    assert final.attempt.code == "# G0"  # canonical bridged
    assert final.verification is not None
    assert final.verification.overall_pass is True


def test_full_mode_candidates_deduped_no_duplication() -> None:
    """reducer 멱등 — executor/record/finalize full-state 재emit 에도 candidates=3."""
    graph = _full_graph(
        spec=_spec("ans"),
        golden_codes=["# G0", "# G1"],
        golden_origins=["opus", "sonnet"],
    )
    final = _final(graph.invoke(initial_state("run-dedup", TargetAlgorithm.TWO_SUM)))

    assert len(final.candidates) == 3  # 2 golden + 1 brute, 중복 누적 없음
    labels = sorted((c.role, c.origin) for c in final.candidates)
    assert labels == [("brute", "naive"), ("golden", "opus"), ("golden", "sonnet")]


# ---------- 2. synthesis rejected ----------


def test_full_mode_synthesis_disagreement_rejected() -> None:
    graph = _full_graph(
        spec=_spec("ans"),
        golden_codes=["# G0", "# WRONG G1"],
        golden_origins=["opus", "sonnet"],
    )
    final = _final(graph.invoke(initial_state("run-rej", TargetAlgorithm.TWO_SUM)))

    assert final.final_status == "fail_synthesis_rejected"
    assert final.reconciliation is not None
    assert final.reconciliation.all_agree is False
    assert final.reconciliation.canonical_code is None
    assert final.attempt is None  # bridge 미실행


# ---------- 3. verification fail (single-shot) ----------


def test_full_mode_canonical_fails_verification() -> None:
    """synthesis 는 합의(채택)했으나 canonical 이 expected 와 불일치 → 단발 fail."""
    graph = _full_graph(
        spec=_spec("zzz"),  # expected=zzz-* 이지만 runner 는 ans-* 산출 → mismatch
        golden_codes=["# G0", "# G1"],
        golden_origins=["opus", "sonnet"],
    )
    final = _final(graph.invoke(initial_state("run-vfail", TargetAlgorithm.TWO_SUM)))

    assert final.final_status == "fail_verification"
    assert final.reconciliation is not None
    assert final.reconciliation.all_agree is True  # synthesis 는 합의함
    assert final.attempt is not None
    assert final.attempt.code == "# G0"  # bridge 됨
    assert final.verification is not None
    assert final.verification.overall_pass is False


# ---------- 4. canonical mode 무영향 ----------


def test_canonical_mode_uses_linear_coder_path() -> None:
    """mode='canonical' (기본) 은 single coder → executor. synthesis 노드 미경유."""
    graph = build_graph(
        mode="canonical",
        architect_llm=_FixedArchitectLLM(_spec("ans")),
        designer_llm=_FixedDesignerLLM(_design()),
        coder_llm=_FixedCoderLLM("# G0"),
        runner=_MarkerRunner(_by_marker),
        verifier_getter=_no_verifier,
    )
    final = _final(graph.invoke(initial_state("run-canon", TargetAlgorithm.TWO_SUM)))

    assert final.final_status == "success"
    assert final.reconciliation is None  # synthesis 미경유
    assert final.candidates == []
    assert final.attempt is not None
    assert final.attempt.code == "# G0"


# ---------- 5. build guard ----------


def test_full_mode_requires_golden_and_brute() -> None:
    with pytest.raises(ValueError, match="golden_llms"):
        build_graph(mode="full", brute_llm=_FixedCoderLLM("# B"))
