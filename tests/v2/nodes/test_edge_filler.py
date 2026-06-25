"""edge_filler 노드 단위 테스트 (v2, Phase 5a) — canonical golden 으로 resolved_edges 채움.

엣지 의미 golden-defined(RFC §3.3): reconcile canonical 을 각 퇴화 엣지 입력에 실행해
expected 를 채운다. mock runner 로 sandbox 없이 결정론 검증 (sample_filler 테스트 미러).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import ReconciliationResult, ResolvedEdgeCase, TargetAlgorithm
from ipe.v2.nodes import make_edge_filler_node
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


def _state(edges: list[ResolvedEdgeCase], *, canonical: str | None) -> V2State:
    base = initial_v2_state("run", TargetAlgorithm.DIJKSTRA)
    return base.model_copy(
        update={
            "resolved_edges": tuple(edges),
            "reconciliation": ReconciliationResult(
                candidate_count=2,
                all_agree=canonical is not None,
                canonical_code=canonical,
                adopted_origin="opus" if canonical else None,
            ),
        }
    )


def test_fills_edge_expected_from_golden_run() -> None:
    """resolved_edges expected 가 golden 실행 stdout 으로 채워진다 — input/name 보존."""
    edges = [
        ResolvedEdgeCase(name="min", input_text="2 1\n1 2 8\n1\n1", rationale="경계"),
        ResolvedEdgeCase(name="unreachable", input_text="4 2\n1 2 3\n3 4 5\n1\n3"),
    ]
    runner = _ScriptedRunner(
        lambda code, stdin: ("OK", f"out:{stdin.split(chr(10))[0]}")
    )
    out = make_edge_filler_node(runner=runner)(_state(edges, canonical="# GOLDEN"))

    assert [e.name for e in out.resolved_edges] == ["min", "unreachable"]
    assert [e.expected_output for e in out.resolved_edges] == ["out:2 1", "out:4 2"]
    assert out.resolved_edges[0].input_text == "2 1\n1 2 8\n1\n1"  # 입력 보존


def test_failed_edge_stays_pending() -> None:
    """golden 이 특정 엣지에서 실행 실패면 pending(None) 유지 — drop 안 함(진단 보존)."""

    def fn(code: str, stdin: str) -> tuple[str, str]:
        return ("RTE", "") if stdin == "bad" else ("OK", "0")

    edges = [
        ResolvedEdgeCase(name="min", input_text="ok"),
        ResolvedEdgeCase(name="weird", input_text="bad"),
    ]
    out = make_edge_filler_node(runner=_ScriptedRunner(fn))(
        _state(edges, canonical="# GOLDEN")
    )
    by_name = {e.name: e.expected_output for e in out.resolved_edges}
    assert by_name == {"min": "0", "weird": None}  # 실패 엣지 pending 유지


def test_noop_without_canonical_golden() -> None:
    """reconcile reject(canonical None) 면 무변경 — 방어적 no-op."""
    edges = [ResolvedEdgeCase(name="min", input_text="x")]
    runner = _ScriptedRunner(lambda code, stdin: ("OK", "1"))
    out = make_edge_filler_node(runner=runner)(_state(edges, canonical=None))
    assert out.resolved_edges[0].expected_output is None  # 안 채움


def test_noop_without_edges() -> None:
    """resolved_edges 빈(비-graph) 면 no-op — golden 실행 안 함."""
    runner = _ScriptedRunner(lambda code, stdin: ("OK", "1"))
    out = make_edge_filler_node(runner=runner)(_state([], canonical="# GOLDEN"))
    assert out.resolved_edges == ()
