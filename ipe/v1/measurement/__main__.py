"""CLI: ``python -m ipe.v1.measurement --algorithm dijkstra --n 3 --output ...``

env: ANTHROPIC_API_KEY required.

Usage::

    python -m ipe.v1.measurement \\
        --algorithm dijkstra \\
        --n 3 \\
        --output docs/baseline/data/v1-pr-a5-detailed.jsonl

cost: N runs ≈ N × (1 architect Opus + 1 designer Sonnet + 1-N coder Opus +
1-N executor) ≈ $1-2 per run for Dijkstra MVR. N=3 ≈ $3-5.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

from ..main_v1 import _parse_target_algorithm
from ..state import DEFAULT_MAX_ITERATIONS
from .n3_runner import (
    BASELINE_5_ALGORITHMS,
    print_summary,
    run_baseline_5_measurements,
    run_n_measurements,
    write_jsonl,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ipe.v1.measurement",
        description="v1 graph N runs measurement + JSONL 저장 (D안 PR-A5)",
    )
    parser.add_argument(
        "--algorithm",
        type=_parse_target_algorithm,
        default=None,
        help=(
            "target algorithm (single-algo mode). Phase 1+: dijkstra/lis/"
            "segtree/two_sum/bfs"
        ),
    )
    parser.add_argument(
        "--baseline-5",
        action="store_true",
        help=(
            "Phase 2a deliverable: baseline 5 algo (Dijkstra/LIS/SegTree/Two "
            "Sum/BFS) 순회. --algorithm 과 mutually exclusive."
        ),
    )
    parser.add_argument(
        "--n",
        type=int,
        default=3,
        help="number of runs (PRINCIPLES.md 룰 1: N>=3)",
    )
    parser.add_argument(
        "--max-iter",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help=f"max iterations per run (default: {DEFAULT_MAX_ITERATIONS})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="output JSONL path (e.g. docs/baseline/data/v1-pr-a5-detailed.jsonl)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = _build_parser().parse_args(argv)

    if args.baseline_5 and args.algorithm is not None:
        print("[measurement] error: --baseline-5 와 --algorithm 동시 지정 불가")
        return 2
    if not args.baseline_5 and args.algorithm is None:
        print("[measurement] error: --baseline-5 또는 --algorithm 중 하나 필수")
        return 2

    if args.baseline_5:
        algo_list = [a.value for a in BASELINE_5_ALGORITHMS]
        print(
            f"[measurement] start baseline-5 algos={algo_list} "
            f"n_per_algo={args.n} max_iter={args.max_iter}"
        )
        outcomes = run_baseline_5_measurements(
            n=args.n, max_iterations=args.max_iter
        )
    else:
        print(
            f"[measurement] start n={args.n} algorithm={args.algorithm.value} "
            f"max_iter={args.max_iter}"
        )
        outcomes = run_n_measurements(
            n=args.n,
            target_algorithm=args.algorithm,
            max_iterations=args.max_iter,
        )
    write_jsonl(outcomes, args.output)
    print_summary(outcomes)
    print(f"\n[measurement] wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
