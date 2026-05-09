"""End-to-end smoke 테스트 (P12.2) — 5 알고리즘 골든 set.

스펙: IMPLEMENTATION_ROADMAP §1 P12.2
범위: 실제 Anthropic API + RlimitRunner sandbox로 full pipeline 실행.

**주의**: ``@pytest.mark.e2e`` marker — pytest 기본 실행에서 skip.
manual trigger:

    pytest tests/e2e/ -m e2e -v          # 명시적 marker
    pytest tests/e2e/test_smoke.py::test_e2e_full_cycle  # 단일 케이스

**비용**: 각 케이스당 ~$1-3 (architect+coder+auditor+generator+evaluator,
모두 Opus). 5개 모두 = ~$5-15. CI에서는 nightly 또는 manual.

DoD 4/5: 5 알고리즘 중 4개 이상 ``final_status='success'`` (LLM 변동성 허용).

골든 set:
1. Two Sum (입출력)
2. BFS shortest path
3. Dijkstra (단일 출발점 최단경로)
4. Segment Tree (구간합/업데이트)
5. DP (Longest Increasing Subsequence)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from ipe.graph import build_graph
from ipe.io import save_result
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.state import ProblemState

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="e2e tests require ANTHROPIC_API_KEY",
    ),
]

# 5 골든 알고리즘 — IMPLEMENTATION_ROADMAP §1 P12.2 명시
GOLDEN_ALGORITHMS = [
    "Two Sum",
    "BFS shortest path",
    "Dijkstra single-source shortest path",
    "Segment Tree range sum",
    "Longest Increasing Subsequence (DP)",
]


def _initial_state(algorithm: str) -> ProblemState:
    return {
        "target_algorithm": algorithm,
        "target_language": "python",
        "iteration_count": 0,
        "max_iter": 8,                # e2e는 retry 여유
        "max_cost_usd": 5.0,          # 케이스당 cap
        "node_retry_budget": {
            "architect": 2, "coder": 4, "auditor": 2, "generator": 2,
        },
        "iteration_history": [],
        "llm_calls": [],
    }


@pytest.mark.parametrize("algorithm", GOLDEN_ALGORITHMS)
def test_e2e_full_cycle(algorithm: str, tmp_path: Path) -> None:
    """단일 알고리즘 e2e — 실제 LLM + sandbox로 full pipeline.

    success / max_iterations / budget_exhausted 모두 valid 종료.
    cost_exceeded는 max_cost_usd 너무 작은 경우 — 본 테스트에선 발생 안 해야 함.
    """
    run_id = f"e2e_{algorithm.replace(' ', '_').lower()[:20]}"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    db_path = run_dir / "checkpoint.db"

    runner = RlimitRunner()
    tracker = LLMCallTracker(run_id, run_dir / "llm_traces")

    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = build_graph(
            tracker=tracker, runner=runner,
            workdir_root=tmp_path / "wd", checkpointer=saver,
        )
        config = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": 100,
        }
        final = graph.invoke(_initial_state(algorithm), config=config)

    final_status = final.get("final_status")
    # cost_exceeded는 본 테스트에서 발생하면 환경 문제
    assert final_status != "cost_exceeded", (
        "unexpected cost_exceeded — check max_cost_usd or LLM pricing"
    )
    # 산출물 영속화 (P10) 검증
    save_result(final, run_dir)
    assert (run_dir / "problem.json").exists()
    assert (run_dir / "problem.md").exists()
    # final_status 보고 — DoD: 5/5 중 4+ success 기대
    print(f"\n[e2e] {algorithm}: final_status={final_status}")
