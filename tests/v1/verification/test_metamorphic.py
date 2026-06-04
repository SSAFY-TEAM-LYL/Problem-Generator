"""metamorphic checker 단위 테스트 (Phase 3 M1, 범용 관계).

determinism 검증을 위해 mock runner 가 (code, stdin, call_index) 를 fn 에 전달 —
재실행 시 출력을 바꿔 nondeterminism 을 시뮬레이트한다.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.verification import run_metamorphic

CODE = "# sol\nprint(1)"


class _CountingRunner:
    """fn(code, stdin, call_index) -> (status, stdout). call_index 는 전역 증가."""

    def __init__(self, fn: Callable[[str, str, int], tuple[str, str]]) -> None:
        self._fn = fn
        self._n = 0

    def run(self, spec: RunSpec) -> RunResult:
        code = (Path(spec.cwd) / "sol.py").read_text(encoding="utf-8")
        status, stdout = self._fn(code, spec.stdin, self._n)
        self._n += 1
        return RunResult(
            status=status,  # type: ignore[arg-type]
            returncode=0 if status == "OK" else 1,
            stdout=stdout,
            stderr="" if status == "OK" else "boom",
            elapsed_ms=1,
        )


def _stable_ok(_code: str, stdin: str, _n: int) -> tuple[str, str]:
    return ("OK", f"out:{stdin}")


def test_all_pass_when_stable_and_well_formed():
    report = run_metamorphic(
        code=CODE, inputs=["a", "b"], runner=_CountingRunner(_stable_ok)
    )
    assert report.all_passed is True
    assert report.violations == ()


def test_determinism_violation_when_output_varies_across_runs():
    def fn(_code: str, _stdin: str, n: int) -> tuple[str, str]:
        # 같은 입력인데 호출마다 다른 출력 → nondeterministic
        return ("OK", f"r{n}")

    report = run_metamorphic(
        code=CODE, inputs=["x"], runner=_CountingRunner(fn), repeats=2
    )
    assert report.all_passed is False
    det = [v for v in report.violations if v.relation == "determinism"]
    assert len(det) == 1
    assert det[0].input_text == "x"


def test_well_formed_violation_on_empty_output():
    def fn(_code: str, _stdin: str, _n: int) -> tuple[str, str]:
        return ("OK", "   \n")  # OK 지만 빈 출력

    report = run_metamorphic(code=CODE, inputs=["x"], runner=_CountingRunner(fn))
    wf = [v for v in report.violations if v.relation == "well_formed"]
    assert len(wf) == 1


def test_well_formed_violation_on_crash():
    def fn(_code: str, _stdin: str, _n: int) -> tuple[str, str]:
        return ("RTE", "")

    report = run_metamorphic(code=CODE, inputs=["x"], runner=_CountingRunner(fn))
    assert report.all_passed is False
    wf = [v for v in report.violations if v.relation == "well_formed"]
    assert len(wf) == 1


def test_well_formed_violation_on_traceback_leak():
    def fn(_code: str, _stdin: str, _n: int) -> tuple[str, str]:
        # status OK 인데 stdout 에 Traceback 누출
        return ("OK", "Traceback (most recent call last):\n  ...\nValueError")

    report = run_metamorphic(code=CODE, inputs=["x"], runner=_CountingRunner(fn))
    wf = [v for v in report.violations if v.relation == "well_formed"]
    assert len(wf) == 1


def test_empty_inputs_not_all_passed():
    report = run_metamorphic(code=CODE, inputs=[], runner=_CountingRunner(_stable_ok))
    assert report.total == 0
    assert report.all_passed is False
