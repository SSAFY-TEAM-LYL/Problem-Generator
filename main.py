"""IPE CLI 진입점.

스펙: ARCHITECTURE.md §3.1, IMPLEMENTATION_ROADMAP §1 P4.4

P4 minimal:
    python main.py --algorithm "Two Sum" --language python

Pipeline: build_graph → invoke → stdout summary.
P5/P6에서 Phase B/C, P7에서 conditional routing, P8에서 --resume/--replay,
P10에서 outputs/<run_id>/problem.json 영속화.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ipe.graph import build_graph
from ipe.observability import LLMCallTracker
from ipe.sandbox.selector import pick_runner
from ipe.state import ProblemState

DEFAULT_MAX_ITER = 5
DEFAULT_MAX_COST_USD = 5.0
OUTPUTS_ROOT = Path("outputs")
WORKDIR_ROOT = Path("workdir")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="ipe",
        description="Infinite Problem Engine — algorithmic problem generator",
    )
    ap.add_argument(
        "--algorithm",
        required=True,
        help='target algorithm category (e.g., "Two Sum", "Dijkstra")',
    )
    ap.add_argument(
        "--language",
        choices=["python", "java"],
        default="python",
    )
    ap.add_argument(
        "--max-iter",
        type=int,
        default=DEFAULT_MAX_ITER,
        help=f"global iteration safety net (default {DEFAULT_MAX_ITER})",
    )
    ap.add_argument(
        "--max-cost-usd",
        type=float,
        default=DEFAULT_MAX_COST_USD,
        help=f"USD cost guard (default {DEFAULT_MAX_COST_USD})",
    )
    ap.add_argument(
        "--sandbox",
        choices=["auto", "docker", "sandboxexec", "rlimit"],
        default="auto",
    )
    ap.add_argument(
        "--strict-sandbox",
        action="store_true",
        help="abort if isolation_self_test fails (P5+ implementation)",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _parse_args(argv)

    run_id = uuid.uuid4().hex[:12]
    run_dir = OUTPUTS_ROOT / run_id
    traces_dir = run_dir / "llm_traces"

    runner = pick_runner(args.sandbox, verbose=True)
    tracker = LLMCallTracker(run_id, traces_dir)

    initial_state: ProblemState = {
        "run_id": run_id,
        "target_algorithm": args.algorithm,
        "target_language": args.language,
        "iteration_count": 0,
        "max_iter": args.max_iter,
        "max_cost_usd": args.max_cost_usd,
    }

    print(
        f"=== IPE run_id={run_id} algo={args.algorithm!r} lang={args.language} ===",
        file=sys.stderr,
    )
    print(f"sandbox tier: {runner.tier}", file=sys.stderr)

    graph = build_graph(
        tracker=tracker, runner=runner, workdir_root=WORKDIR_ROOT
    )
    config = {"recursion_limit": max(50, args.max_iter * 12)}
    final_state: dict[str, Any] = graph.invoke(initial_state, config=config)

    final_status = final_state.get("final_status")
    print(f"\n=== final_status: {final_status} ===", file=sys.stderr)
    print(
        f"last_failed_node: {final_state.get('last_failed_node')}",
        file=sys.stderr,
    )

    # P10에서 io.save_result로 대체. P4 단계는 stdout JSON summary만.
    summary = {
        "run_id": run_id,
        "final_status": final_status,
        "last_failed_node": final_state.get("last_failed_node"),
        "iteration_count": final_state.get("iteration_count"),
        "problem_title": final_state.get("problem_title"),
        "execution_results": final_state.get("execution_results", []),
        "feedback_message": final_state.get("feedback_message"),
        "llm_calls_count": len(final_state.get("llm_calls") or []),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if final_status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
