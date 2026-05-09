"""IPE CLI 진입점.

스펙: ARCHITECTURE.md §3.1, IMPLEMENTATION_ROADMAP §1 P4.4 / P8.2 / P8.4

Usage::

    python main.py --algorithm "Two Sum" --language python  # 새 run
    python main.py --resume <run_id>                         # P8.2 crash 후 재개
    python main.py --replay <run_id>                         # P8.4 LLM 0 호출 재현
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, cast

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver

from ipe.graph import build_graph
from ipe.io import save_result
from ipe.logging_config import setup_logging
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
    ap.add_argument("--algorithm", help='target algorithm (required for new runs)')
    ap.add_argument("--language", choices=["python", "java"], default="python")
    ap.add_argument("--max-iter", type=int, default=DEFAULT_MAX_ITER)
    ap.add_argument("--max-cost-usd", type=float, default=DEFAULT_MAX_COST_USD)
    ap.add_argument(
        "--sandbox",
        choices=["auto", "docker", "sandboxexec", "rlimit"], default="auto",
    )
    ap.add_argument("--strict-sandbox", action="store_true")
    ap.add_argument("--resume", metavar="RUN_ID", help="resume from checkpoint.db")
    ap.add_argument("--replay", metavar="RUN_ID", help="replay from llm_traces")
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
        "node_retry_budget": {"architect": 2, "coder": 4, "auditor": 2, "generator": 2},
        "iteration_history": [],
        "llm_calls": [],
    }


def _setup_run(args: argparse.Namespace) -> tuple[str, Path, Path, Path]:
    """run_id / run_dir / traces_dir / db_path 결정 + resume/replay 산출물 검증.

    raises:
        FileNotFoundError: resume/replay에 필요한 디렉토리/파일 부재.
    """
    if args.resume or args.replay:
        run_id = args.resume or args.replay
        run_dir = OUTPUTS_ROOT / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"run_id directory not found: {run_dir}")
    else:
        run_id = uuid.uuid4().hex[:12]
        run_dir = OUTPUTS_ROOT / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

    traces_dir = run_dir / "llm_traces"
    db_path = run_dir / "checkpoint.db"

    if args.resume and not db_path.exists():
        raise FileNotFoundError(f"checkpoint not found: {db_path}")
    if args.replay and not traces_dir.exists():
        raise FileNotFoundError(f"traces not found: {traces_dir}")
    return run_id, run_dir, traces_dir, db_path


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    setup_logging(level="INFO")  # P11: structured JSON logs to stdout
    args = _parse_args(argv)

    try:
        run_id, run_dir, traces_dir, db_path = _setup_run(args)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    runner = pick_runner(args.sandbox, verbose=True)
    tracker: LLMCallTracker = (
        ReplayTracker(run_id, traces_dir) if args.replay
        else LLMCallTracker(run_id, traces_dir)
    )

    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = build_graph(
            tracker=tracker, runner=runner,
            workdir_root=WORKDIR_ROOT, checkpointer=saver,
        )
        config: dict[str, Any] = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": max(50, args.max_iter * 12),
        }
        if args.resume:
            print(f"=== IPE resume run_id={run_id} (sandbox={runner.tier}) ===",
                  file=sys.stderr)
            final_state: dict[str, Any] = graph.invoke(None, config=config)
        else:
            algo = args.algorithm if not args.replay else "(replay)"
            print(f"=== IPE run_id={run_id} algo={algo!r} lang={args.language} "
                  f"(sandbox={runner.tier}) ===", file=sys.stderr)
            final_state = graph.invoke(_initial_state(run_id, args), config=config)

    final_status = final_state.get("final_status")
    print(f"\n=== final_status: {final_status} ===", file=sys.stderr)
    print(f"last_failed_node: {final_state.get('last_failed_node')}", file=sys.stderr)

    save_result(cast(ProblemState, final_state), run_dir)  # P10
    print(f"saved outputs to {run_dir}", file=sys.stderr)

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
