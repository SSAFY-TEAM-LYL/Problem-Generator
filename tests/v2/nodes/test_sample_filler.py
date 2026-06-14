"""sample_filler 노드 단위 테스트 (v2) — canonical golden 실행으로 sample expected 채움.

사용자 원칙(정답은 golden 부트스트랩): spec_bridge 가 sample input 만 저작(expected 빈
값)하고, 이 노드가 reconcile canonical golden 실행으로 expected 를 채운다. mock runner
주입으로 sandbox 없이 결정론 검증 (reconcile 테스트 패턴 미러).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import (
    IOContract,
    ProblemSpec,
    ReconciliationResult,
    SampleTestCase,
    TargetAlgorithm,
)
from ipe.v2.nodes import make_sample_filler_node
from ipe.v2.state import V2State, initial_v2_state


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


def _spec(samples: list[SampleTestCase]) -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="t",
        description="은닉 지문",
        io_contract=IOContract(input_format="N", output_format="정수"),
        sample_testcases=samples,
    )


def _state(spec: ProblemSpec | None, *, canonical: str | None) -> V2State:
    base = initial_v2_state("run", TargetAlgorithm.DIJKSTRA)
    update: dict[str, object] = {}
    if spec is not None:
        update["spec"] = spec
    update["reconciliation"] = ReconciliationResult(
        candidate_count=2,
        all_agree=canonical is not None,
        canonical_code=canonical,
        adopted_origin="opus" if canonical else None,
    )
    return base.model_copy(update=update)


def test_fills_expected_from_golden_run() -> None:
    """sample expected 가 golden 실행 stdout 으로 채워진다 — input 은 보존."""
    spec = _spec(
        [
            SampleTestCase(input_text="3", expected_output=""),
            SampleTestCase(input_text="5", expected_output=""),
            SampleTestCase(input_text="7", expected_output=""),
        ]
    )
    runner = _ScriptedRunner(lambda code, stdin: ("OK", f"ans:{stdin}"))
    out = make_sample_filler_node(runner=runner)(_state(spec, canonical="# GOLDEN"))

    filled = out.spec
    assert filled is not None
    assert [s.input_text for s in filled.sample_testcases] == ["3", "5", "7"]
    assert [s.expected_output for s in filled.sample_testcases] == [
        "ans:3",
        "ans:5",
        "ans:7",
    ]


def test_keeps_failed_sample_with_empty_expected() -> None:
    """golden 이 특정 입력 파싱 실패(RTE)면 원본 유지(빈 expected) — drop 하면 min 3
    제약 위반. 길이 보존하고 executor 가 형식 불일치로 fail 처리하게 둔다."""

    def fn(code: str, stdin: str) -> tuple[str, str]:
        return ("RTE", "") if stdin == "bad" else ("OK", f"ans:{stdin}")

    spec = _spec(
        [
            SampleTestCase(input_text="3", expected_output=""),
            SampleTestCase(input_text="bad", expected_output=""),
            SampleTestCase(input_text="5", expected_output=""),
        ]
    )
    out = make_sample_filler_node(runner=_ScriptedRunner(fn))(
        _state(spec, canonical="# GOLDEN")
    )

    filled = out.spec
    assert filled is not None
    cases = {s.input_text: s.expected_output for s in filled.sample_testcases}
    assert cases == {"3": "ans:3", "bad": "", "5": "ans:5"}  # 길이 보존, bad 빈 채


def test_noop_without_canonical_golden() -> None:
    """reconcile reject(canonical None) 면 무변경 — 방어적 no-op."""
    spec = _spec(
        [
            SampleTestCase(input_text="3", expected_output=""),
            SampleTestCase(input_text="4", expected_output=""),
            SampleTestCase(input_text="5", expected_output=""),
        ]
    )
    runner = _ScriptedRunner(lambda code, stdin: ("OK", "x"))
    out = make_sample_filler_node(runner=runner)(_state(spec, canonical=None))

    filled = out.spec
    assert filled is not None
    assert all(s.expected_output == "" for s in filled.sample_testcases)  # 안 채워짐


def test_noop_without_spec() -> None:
    runner = _ScriptedRunner(lambda code, stdin: ("OK", "x"))
    out = make_sample_filler_node(runner=runner)(_state(None, canonical="# G"))
    assert out.spec is None
