"""Baseline CLI — 단일 LLM baseline 측정 + 보고.

사용 예::

    python -m ipe.baseline run "BFS"                    # 1 algorithm 측정 (stdout JSON)
    python -m ipe.baseline run "BFS" --out result.json  # 결과를 file 저장
    python -m ipe.baseline batch --out results.jsonl    # 5 default algorithms 측정
    python -m ipe.baseline batch "Two Sum" "LIS" --out results.jsonl

spec: docs/PRINCIPLES.md §3.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from ipe.baseline.runner import BaselineResult, run_baseline

DEFAULT_ALGORITHMS: tuple[str, ...] = (
    "Two Sum", "BFS", "Dijkstra", "LIS", "Segment Tree",
)


def _write_or_print(result: BaselineResult, out: Path | None) -> None:
    """결과를 JSON으로 file (out) 또는 stdout에 출력."""
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)


def _cmd_run(args: argparse.Namespace) -> int:
    result = run_baseline(args.algorithm, language=args.language)
    _write_or_print(result, args.out)
    return 0 if result.get("failure_mode") == "ok" else 1


def _cmd_batch(args: argparse.Namespace) -> int:
    algorithms: list[str] = list(args.algorithms) if args.algorithms else list(DEFAULT_ALGORITHMS)
    results: list[BaselineResult] = []
    for algo in algorithms:
        print(f"=== baseline: {algo} ===", file=sys.stderr)
        r = run_baseline(algo, language=args.language)
        results.append(r)
        print(
            f"  pass_rate={r.get('pass_rate', 0):.2f} "
            f"({r.get('sample_pass', 0)}/{r.get('sample_count', 0)}) "
            f"mode={r.get('failure_mode')}",
            file=sys.stderr,
        )

    if args.out:
        # JSONL — 1 row/algorithm
        lines = [json.dumps(r, ensure_ascii=False) for r in results]
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        for r in results:
            print(json.dumps(r, ensure_ascii=False))

    # exit code: 모든 algorithm 통과 시 0, 하나라도 fail 시 1
    all_ok = all(r.get("failure_mode") == "ok" for r in results)
    return 0 if all_ok else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ipe.baseline",
        description="Single-LLM baseline measurement (1 Opus call, no IPE pipeline)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="1 algorithm baseline 측정")
    p_run.add_argument("algorithm", help='target algorithm (e.g. "BFS")')
    p_run.add_argument("--language", default="python", choices=["python"])
    p_run.add_argument("--out", type=Path, default=None, help="결과 file (없으면 stdout)")
    p_run.set_defaults(func=_cmd_run)

    p_batch = sub.add_parser(
        "batch", help=f"여러 algorithm 측정 (default: {', '.join(DEFAULT_ALGORITHMS)})"
    )
    p_batch.add_argument(
        "algorithms", nargs="*", help="알고리즘 이름 리스트 (생략 시 default)"
    )
    p_batch.add_argument("--language", default="python", choices=["python"])
    p_batch.add_argument("--out", type=Path, default=None, help="JSONL out file")
    p_batch.set_defaults(func=_cmd_batch)

    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()  # ANTHROPIC_API_KEY 등 환경 변수 로드 (main.py 와 동일)
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
