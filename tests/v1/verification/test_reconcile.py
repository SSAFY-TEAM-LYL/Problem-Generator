"""reconcile() 단위 테스트 (Phase 3 M2 step 2) — Reconciler(N5) 코드 로직.

K golden + brute 후보를 reference golden 기준 differential 로 상호 비교 →
전부 일치하면 canonical 채택, 하나라도 불일치면 reject 신호. runner 주입 —
mock 으로 sandbox 없이 결정론 검증 (tier_measure 테스트 패턴 미러).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import SolutionCandidate
from ipe.v1.verification.reconcile import reconcile


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


def _by_marker(code: str, stdin: str) -> tuple[str, str]:
    """code marker 로 출력 결정. WRONG 은 다른 답, CRASH 는 RTE."""
    if "CRASH" in code:
        return ("RTE", "")
    if "WRONG" in code:
        return ("OK", f"wrong-{stdin}")
    return ("OK", f"ans-{stdin}")  # GOLDEN/BRUTE correct → 동일 답


_INPUTS = ["i1", "i2", "i3"]


def _golden(origin: str, marker: str = "GOLDEN", idx: int = 0) -> SolutionCandidate:
    return SolutionCandidate(
        role="golden", origin=origin, code=f"# {marker} {origin}", fanout_index=idx
    )


def _brute(origin: str = "naive", marker: str = "BRUTE") -> SolutionCandidate:
    return SolutionCandidate(role="brute", origin=origin, code=f"# {marker} {origin}")


def test_all_agree_adopts_reference_golden() -> None:
    cands = [_golden("opus", idx=0), _golden("sonnet", idx=1), _brute()]
    r = reconcile(candidates=cands, inputs=_INPUTS, runner=_ScriptedRunner(_by_marker))
    assert r.all_agree is True
    assert r.candidate_count == 3
    assert r.adopted_origin == "opus"  # 최소 fanout_index reference
    assert r.canonical_code == "# GOLDEN opus"
    assert r.disagreements == ()


def test_golden_disagreement_rejects() -> None:
    cands = [_golden("opus", idx=0), _golden("sonnet", marker="WRONG", idx=1), _brute()]
    r = reconcile(candidates=cands, inputs=_INPUTS, runner=_ScriptedRunner(_by_marker))
    assert r.all_agree is False
    assert r.canonical_code is None
    assert r.adopted_origin is None
    assert any("sonnet" in d for d in r.disagreements)


def test_brute_disagreement_rejects() -> None:
    cands = [_golden("opus", idx=0), _brute(marker="WRONG")]
    r = reconcile(candidates=cands, inputs=_INPUTS, runner=_ScriptedRunner(_by_marker))
    assert r.all_agree is False
    assert r.canonical_code is None


def test_crash_candidate_rejects() -> None:
    cands = [_golden("opus", idx=0), _golden("sonnet", marker="CRASH", idx=1), _brute()]
    r = reconcile(candidates=cands, inputs=_INPUTS, runner=_ScriptedRunner(_by_marker))
    assert r.all_agree is False
    assert r.canonical_code is None


def test_single_golden_no_crosscheck_rejects() -> None:
    """golden 1개 + brute 없음 → 교차검증 불가 → all_agree=False."""
    cands = [_golden("opus", idx=0)]
    r = reconcile(candidates=cands, inputs=_INPUTS, runner=_ScriptedRunner(_by_marker))
    assert r.all_agree is False
    assert r.canonical_code is None
    assert r.candidate_count == 1


def test_no_golden_rejects() -> None:
    """golden 부재 (brute 만) → canonical 채택 불가."""
    cands = [_brute()]
    r = reconcile(candidates=cands, inputs=_INPUTS, runner=_ScriptedRunner(_by_marker))
    assert r.all_agree is False
    assert r.canonical_code is None
    assert any("golden" in d.lower() for d in r.disagreements)


def test_golden_brute_only_pair_agrees() -> None:
    """golden 1 + brute 1 일치 → 교차검증 성립 → canonical 채택."""
    cands = [_golden("opus", idx=0), _brute()]
    r = reconcile(candidates=cands, inputs=_INPUTS, runner=_ScriptedRunner(_by_marker))
    assert r.all_agree is True
    assert r.adopted_origin == "opus"
    assert r.canonical_code == "# GOLDEN opus"


def test_empty_inputs_cannot_confirm() -> None:
    """샘플 입력 0개 → differential 신호 없음 → all_agree=False (vacuous 금지)."""
    cands = [_golden("opus", idx=0), _brute()]
    r = reconcile(candidates=cands, inputs=[], runner=_ScriptedRunner(_by_marker))
    assert r.all_agree is False
