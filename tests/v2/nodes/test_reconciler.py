"""v2 reconciler 노드 단위 테스트 (Phase 5a) — sample + 퇴화 엣지 differential 확장.

v1 reconcile 와 동일 채택 로직이지만 differential 입력에 backbone 파생 퇴화 엣지를 더한다
(RFC §6 Tier B). 골든 합의 → canonical 채택 + resolved_edges(pending) 기록; 엣지에서 불합의
→ 그 입력이 witness 인 reject. graph_shape 핀된 graph 만 엣지 확장(비-graph=samples only).
mock runner 로 sandbox 없이 결정론 검증.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import (
    ConstraintRange,
    GraphShape,
    IOContract,
    IOFieldSpec,
    IOSchema,
    ProblemBlueprint,
    ProblemSpec,
    SampleTestCase,
    SolutionCandidate,
    TargetAlgorithm,
)
from ipe.v2.generation.input_gen import derive_degenerate_inputs
from ipe.v2.nodes import make_v2_reconciler_node
from ipe.v2.state import V2State, initial_v2_state


class _RecordingRunner:
    """fn(code, stdin) -> (status, stdout); differential 의 stdin 들을 ``seen`` 에 기록."""

    def __init__(self, fn: Callable[[str, str], tuple[str, str]]) -> None:
        self._fn = fn
        self.seen: list[str] = []

    def run(self, spec: RunSpec) -> RunResult:
        code = (Path(spec.cwd) / "sol.py").read_text(encoding="utf-8")
        self.seen.append(spec.stdin)
        status, stdout = self._fn(code, spec.stdin)
        return RunResult(
            status=status,  # type: ignore[arg-type]
            returncode=0 if status == "OK" else 1,
            stdout=stdout,
            stderr="" if status == "OK" else "boom",
            elapsed_ms=1,
        )


def _graph_blueprint() -> ProblemBlueprint:
    io = IOSchema(
        inputs=(
            IOFieldSpec(
                name="grid",
                type="weighted_edges",
                size_range=ConstraintRange(name="grid", min_value=2, max_value=10),
                value_range=ConstraintRange(name="w", min_value=1, max_value=9),
                graph_shape=GraphShape(
                    directed=False, connectivity="maybe_disconnected"
                ),
            ),
            IOFieldSpec(name="s", type="int", references="grid"),
            IOFieldSpec(name="t", type="int", references="grid"),
        ),
        output_type="int",
        output_format="x",
    )
    return ProblemBlueprint(
        reduction_core=TargetAlgorithm.DIJKSTRA, domain="d", io_schema=io
    )


def _spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="t",
        description="은닉 지문",
        io_contract=IOContract(input_format="x", output_format="y"),
        sample_testcases=[
            SampleTestCase(input_text="s1", expected_output=""),
            SampleTestCase(input_text="s2", expected_output=""),
            SampleTestCase(input_text="s3", expected_output=""),
        ],
    )


def _state(
    candidates: list[SolutionCandidate], *, with_blueprint: bool = True
) -> V2State:
    base = initial_v2_state("run", TargetAlgorithm.DIJKSTRA)
    update: dict[str, object] = {"candidates": candidates, "spec": _spec()}
    if with_blueprint:
        update["blueprint"] = _graph_blueprint()
    return base.model_copy(update=update)


def _pair() -> list[SolutionCandidate]:
    return [
        SolutionCandidate(
            role="golden", origin="opus", code="# golden", fanout_index=0
        ),
        SolutionCandidate(
            role="brute", origin="naive", code="# brute", fanout_index=0
        ),
    ]


def test_agree_adopts_canonical_and_records_edges() -> None:
    """골든·brute 가 sample+엣지 전부 합의 → canonical 채택 + resolved_edges(pending) 기록."""
    runner = _RecordingRunner(lambda code, stdin: ("OK", "SAME"))
    out = make_v2_reconciler_node(runner)(_state(_pair()))

    rec = out["reconciliation"]
    assert rec.all_agree is True
    assert rec.canonical_code == "# golden"
    # 퇴화 엣지 기록(pending) — edge_filler 가 나중에 expected 채움
    edges = out["resolved_edges"]
    assert [e.name for e in edges] == ["min", "unreachable"]
    assert all(e.expected_output is None for e in edges)


def test_edge_inputs_are_added_to_differential() -> None:
    """핵심: backbone 파생 퇴화 입력이 실제 differential 에 들어간다 (samples 만이 아님)."""
    degens = derive_degenerate_inputs(_graph_blueprint().io_schema)
    edge_texts = {text for _name, text, _rat in degens}
    runner = _RecordingRunner(lambda code, stdin: ("OK", "SAME"))
    make_v2_reconciler_node(runner)(_state(_pair()))
    # 샘플 + 엣지 모두 실행됨
    assert {"s1", "s2", "s3"} <= set(runner.seen)
    assert edge_texts <= set(runner.seen)  # 엣지 입력이 diff 됨


def test_edge_divergence_rejects_with_witness() -> None:
    """ill-posed: brute 가 unreachable 엣지에서만 다른 답 → reject (witness 가 그 입력)."""
    degens = derive_degenerate_inputs(_graph_blueprint().io_schema)
    unreachable_input = next(t for n, t, _r in degens if n == "unreachable")

    def fn(code: str, stdin: str) -> tuple[str, str]:
        if code == "# brute" and stdin == unreachable_input:
            return ("OK", "DIVERGE")  # 도달 불가 의미 불합의
        return ("OK", "AGREE")

    out = make_v2_reconciler_node(_RecordingRunner(fn))(_state(_pair()))
    rec = out["reconciliation"]
    assert rec.all_agree is False
    assert rec.canonical_code is None
    assert rec.disagreements  # witness 진단 존재
    # 엣지는 여전히 기록(reject 라도 진단/Phase5b 근거)
    assert [e.name for e in out["resolved_edges"]] == ["min", "unreachable"]


def test_no_blueprint_diffs_samples_only() -> None:
    """blueprint 부재(또는 비-graph) → 엣지 파생 0 → samples 만 diff."""
    runner = _RecordingRunner(lambda code, stdin: ("OK", "SAME"))
    out = make_v2_reconciler_node(runner)(_state(_pair(), with_blueprint=False))
    assert out["resolved_edges"] == ()
    assert set(runner.seen) == {"s1", "s2", "s3"}  # 엣지 입력 없음
    assert out["reconciliation"].all_agree is True
