"""suite assembler 엔진 단위 테스트 (Phase 3 M4 step4).

assemble_suite(pending, golden_code, runner, origin): golden 실행으로 expected 채움 +
실행 실패 케이스 drop + 전부 실패 시 ValueError. mock runner 로 sandbox 없이 결정론.
"""

from __future__ import annotations

import pytest

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import GeneratedTestCase, TestSuite
from ipe.v2.generation.assembler import assemble_suite


class _EchoRunner:
    """golden 출력 = f'ans:{stdin}'. 'BAD' 포함 입력은 RTE(실행 실패)."""

    def run(self, spec: RunSpec) -> RunResult:
        if "BAD" in spec.stdin:
            return RunResult(
                status="RTE", returncode=1, stdout="", stderr="boom", elapsed_ms=1
            )
        return RunResult(
            status="OK",
            returncode=0,
            stdout=f"ans:{spec.stdin}\n",
            stderr="",
            elapsed_ms=1,
        )


def _pending(*inputs: str) -> TestSuite:
    return TestSuite(
        cases=tuple(
            GeneratedTestCase(input_text=i, category="small") for i in inputs
        )
    )


def test_assemble_fills_expected_from_golden_stdout() -> None:
    suite = assemble_suite(
        _pending("1", "2", "3"), "# golden", runner=_EchoRunner(), golden_origin="opus"
    )
    assert suite.is_assembled is True
    assert suite.golden_origin == "opus"
    assert [c.expected_output for c in suite.cases] == ["ans:1", "ans:2", "ans:3"]


def test_assemble_drops_cases_golden_cannot_run() -> None:
    suite = assemble_suite(
        _pending("1", "BAD", "3"), "# g", runner=_EchoRunner(), golden_origin="g"
    )
    assert len(suite.cases) == 2  # BAD drop
    assert all(c.expected_output is not None for c in suite.cases)
    assert [c.input_text for c in suite.cases] == ["1", "3"]


def test_assemble_raises_when_all_cases_fail() -> None:
    with pytest.raises(ValueError, match="하나도 실행") as exc_info:
        assemble_suite(
            _pending("BAD1", "BAD2"), "# g", runner=_EchoRunner(), golden_origin="g"
        )
    msg = str(exc_info.value)
    assert "RTE" in msg  # 첫 실패 status 진단 (e2e all-fail 원인 분석용)
    assert "boom" in msg  # 첫 실패 stderr
    assert "BAD1" in msg  # 첫 실패 입력 head
