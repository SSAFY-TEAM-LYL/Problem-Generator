"""IPE CLI 진입점.

스펙: ARCHITECTURE.md §3.1, IMPLEMENTATION_ROADMAP §1 P4.4 / P8.2 / P8.4

Usage::

    python main.py --algorithm "Two Sum" --language python  # 새 run
    python main.py --resume <run_id>                         # crash 후 재개 (P8.2)
    python main.py --replay <run_id>                         # LLM 0 호출 재현 (P8.4)

Pipeline: build_graph(checkpointer) → invoke(thread_id=run_id) → stdout summary.

P8: SqliteSaver로 노드 단위 영속화 (``outputs/<run_id>/checkpoint.db``).
P10에서 outputs/<run_id>/problem.json 영속화 + 산출물 집계 추가.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver

from ipe.graph import build_graph
from ipe.observability import LLMCallTracker, ReplayTracker
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
        help='target algorithm category (e.g., "Two Sum", "Dijkstra"); required for new runs',
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
    ap.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="resume an aborted run from outputs/<RUN_ID>/checkpoint.db (P8.2)",
    )
    ap.add_argument(
        "--replay",
        metavar="RUN_ID",
        help="re-run from outputs/<RUN_ID>/llm_traces without LLM calls (P8.4)",
    )
    args = ap.parse_args(argv)
    if args.resume and args.replay:
        ap.error("--resume and --replay are mutually exclusive")
    if not args.resume and not args.replay and not args.algorithm:
        ap.error("--algorithm is required for new runs")
    return args


def _initial_state(run_id: str, args: argparse.Namespace) -> ProblemState:
    """SPEC §5 default node_retry_budget으로 새 ProblemState 빌드."""
    return {
        "run_id": run_id,
        "target_algorithm": args.algorithm,
        "target_language": args.language,
        "iteration_count": 0,
        "max_iter": args.max_iter,
        "max_cost_usd": args.max_cost_usd,
        "node_retry_budget": {
            "architect": 2,
            "coder": 4,
            "auditor": 2,
            "generator": 2,
        },
        "iteration_history": [],
        "llm_calls": [],
    }


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _parse_args(argv)

    # run_id resolve — resume/replay는 인자값 사용, 그 외는 새로 생성
    if args.resume or args.replay:
        run_id = args.resume or args.replay
        run_dir = OUTPUTS_ROOT / run_id
        if not run_dir.exists():
            print(f"run_id directory not found: {run_dir}", file=sys.stderr)
            return 2
    else:
        run_id = uuid.uuid4().hex[:12]
        run_dir = OUTPUTS_ROOT / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

    traces_dir = run_dir / "llm_traces"
    db_path = run_dir / "checkpoint.db"

    if args.resume and not db_path.exists():
        print(f"checkpoint not found: {db_path}", file=sys.stderr)
        return 2
    if args.replay and not traces_dir.exists():
        print(f"traces not found: {traces_dir}", file=sys.stderr)
        return 2

    runner = pick_runner(args.sandbox, verbose=True)

    # tracker swap — replay 모드는 ReplayTracker로 LLM 호출 우회
    tracker: LLMCallTracker
    if args.replay:
        tracker = ReplayTracker(run_id, traces_dir)
    else:
        tracker = LLMCallTracker(run_id, traces_dir)

    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = build_graph(
            tracker=tracker,
            runner=runner,
            workdir_root=WORKDIR_ROOT,
            checkpointer=saver,
        )
        config: dict[str, Any] = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": max(50, args.max_iter * 12),
        }

        if args.resume:
            print(
                f"=== IPE resume run_id={run_id} (sandbox tier={runner.tier}) ===",
                file=sys.stderr,
            )
            final_state: dict[str, Any] = graph.invoke(None, config=config)
        else:
            algo = args.algorithm if not args.replay else "(replay)"
            print(
                f"=== IPE run_id={run_id} algo={algo!r} lang={args.language} "
                f"(sandbox tier={runner.tier}) ===",
                file=sys.stderr,
            )
            final_state = graph.invoke(_initial_state(run_id, args), config=config)

    final_status = final_state.get("final_status")
    print(f"\n=== final_status: {final_status} ===", file=sys.stderr)
    print(
        f"last_failed_node: {final_state.get('last_failed_node')}",
        file=sys.stderr,
    )

    # P10에서 io.save_result로 대체. 현재는 stdout JSON summary만.
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
