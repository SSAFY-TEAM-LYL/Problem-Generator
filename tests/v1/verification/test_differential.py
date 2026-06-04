"""differential tester 단위 테스트 (Phase 3 M1).

sandbox 없이 mock runner 로 검증 — runner 는 작성된 sol.py 내용을 읽어
(code, stdin) 에 대한 canned RunResult 를 반환한다. golden/brute 를 marker
문자열로 식별.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.verification import run_differential

GOLDEN = "# GOLDEN\nprint(input())"
BRUTE = "# BRUTE\nprint(input())"


class _ScriptedRunner:
    """주입된 fn(code, stdin) -> (status, stdout) 으로 RunResult 생성."""

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


def _identical_outputs(code: str, stdin: str) -> tuple[str, str]:
    # golden·brute 모두 입력을 그대로 echo → 항상 일치
    return ("OK", f"ans:{stdin}")


def test_all_agree_when_outputs_identical():
    report = run_differential(
        golden_code=GOLDEN,
        brute_code=BRUTE,
        inputs=["1", "2", "3"],
        runner=_ScriptedRunner(_identical_outputs),
    )
    assert report.total == 3
    assert report.all_agreed is True
    assert report.disagreements == ()
    assert report.both_ran == 3


def test_disagreement_detected_on_one_input():
    def fn(code: str, stdin: str) -> tuple[str, str]:
        # 입력 "2" 에서만 golden 과 brute 가 다른 답 → 차분이 잡아야 함
        if stdin == "2":
            return ("OK", "5" if "GOLDEN" in code else "4")
        return ("OK", "same")

    report = run_differential(
        golden_code=GOLDEN,
        brute_code=BRUTE,
        inputs=["1", "2", "3"],
        runner=_ScriptedRunner(fn),
    )
    assert report.all_agreed is False
    assert len(report.disagreements) == 1
    bad = report.disagreements[0]
    assert bad.input_text == "2"
    assert bad.golden_output == "5"
    assert bad.brute_output == "4"


def test_crash_counts_as_disagreement_not_confirmation():
    def fn(code: str, stdin: str) -> tuple[str, str]:
        # brute 가 입력 "9" 에서 crash → agreed 불가 (보수적)
        if stdin == "9" and "BRUTE" in code:
            return ("RTE", "")
        return ("OK", "v")

    report = run_differential(
        golden_code=GOLDEN,
        brute_code=BRUTE,
        inputs=["9"],
        runner=_ScriptedRunner(fn),
    )
    assert report.all_agreed is False
    assert report.both_ran == 0
    assert report.disagreements[0].brute_status == "RTE"


def test_empty_inputs_is_not_all_agreed():
    report = run_differential(
        golden_code=GOLDEN,
        brute_code=BRUTE,
        inputs=[],
        runner=_ScriptedRunner(_identical_outputs),
    )
    assert report.total == 0
    assert report.all_agreed is False  # 신호 없음 → vacuous 통과 금지


def test_whitespace_normalized_before_compare():
    def fn(code: str, stdin: str) -> tuple[str, str]:
        # 같은 값이지만 trailing 공백/개행 차이만 → 정규화 후 일치해야 함
        return ("OK", "1 2 3\n" if "GOLDEN" in code else "  1 2 3  \n\n")

    report = run_differential(
        golden_code=GOLDEN,
        brute_code=BRUTE,
        inputs=["x"],
        runner=_ScriptedRunner(fn),
    )
    assert report.all_agreed is True
