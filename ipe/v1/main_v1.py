"""IPE v1 CLI entrypoint (D안 PR-A4).

Usage::

    ipe-v1 --algorithm dijkstra
    ipe-v1 --algorithm dijkstra --run-id my-run-001 --max-iter 4

env:
    ANTHROPIC_API_KEY (required for production LLM calls)

Phase 1 단순화:
- 지원 algorithm: ``dijkstra`` 만 (Phase 2 에서 LIS/SegmentTree 등 enum 확장).
- observability: stdout 만 (final_status / iterations / sample_results /
  invariant_violations 요약). LangSmith / OTel 통합은 Phase 2+.
- output 영속화 X (PR-A3 기준 in-memory state). 영속화는 Phase 2 catalog 통합.

exit code: 0 on success, 1 on any fail_*.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

from .graph import build_graph
from .persistence import persist_run_outputs
from .schema import TargetAlgorithm
from .state import DEFAULT_MAX_ITERATIONS, V1State, initial_state


def _parse_target_algorithm(value: str) -> TargetAlgorithm:
    """argparse type — 지원 enum value 검증. Phase 2 에서 확장 시 자동 OK."""
    try:
        return TargetAlgorithm(value.lower())
    except ValueError as e:
        valid = [a.value for a in TargetAlgorithm]
        msg = f"unsupported algorithm '{value}'. supported: {valid}"
        raise argparse.ArgumentTypeError(msg) from e


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ipe-v1",
        description=(
            "IPE v1 — D안 architecture (typed structured artifacts + "
            "symbolic verifier)"
        ),
    )
    parser.add_argument(
        "--algorithm",
        type=_parse_target_algorithm,
        required=True,
        help=f"target algorithm (Phase 1: {TargetAlgorithm.DIJKSTRA.value})",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="run identifier (default: random uuid4 short hash)",
    )
    parser.add_argument(
        "--max-iter",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help=f"max iterations (default: {DEFAULT_MAX_ITERATIONS})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="dump spec/design/attempt for diagnosis (verifier engagement debug)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help=(
            "persist run outputs (spec.json/design.json/attempt.py/"
            "verification.json/outcome.json) to <dir>/<run_id>/. "
            "default: outputs/."
        ),
    )
    parser.add_argument(
        "--no-output-dir",
        action="store_true",
        help="비활성화 — outputs/ persistence skip.",
    )
    return parser


def _print_verbose(final: V1State) -> None:
    """spec/design/attempt 전체 출력 — verifier engagement 디버그."""
    print("\n=== VERBOSE DUMP ===")
    if final.spec is not None:
        print(f"\n[spec.target_algorithm] {final.spec.target_algorithm.value}")
        print(f"[spec.title] {final.spec.title}")
        print(f"[spec.io_contract.input_format]\n{final.spec.io_contract.input_format}")
        print(f"[spec.io_contract.output_format]\n{final.spec.io_contract.output_format}")
        for i, s in enumerate(final.spec.sample_testcases):
            print(f"\n--- sample {i} input_text ---")
            print(repr(s.input_text))
            print(f"--- sample {i} expected_output ---")
            print(repr(s.expected_output))
    if final.design is not None:
        print("\n[design.invariants]")
        for inv in final.design.invariants:
            print(f"  - {inv.kind}: {inv.description}")
    if final.attempt is not None:
        print("\n[attempt.code (first 1000 chars)]")
        print(final.attempt.code[:1000])
    print("\n=== END VERBOSE ===\n")


def _print_summary(final: V1State) -> None:
    """final state 요약 stdout. Phase 1 minimal observability."""
    print(f"[v1] final_status={final.final_status} iteration_count={final.iteration}")
    v = final.verification
    if v is None:
        print("[v1] verification: <none> (graph 가 verification 단계 진입 못함)")
        return
    passed_count = sum(1 for sr in v.sample_results if sr.passed)
    print(
        f"[v1] sample_results: {passed_count}/{len(v.sample_results)} passed, "
        f"samples_engaged={v.samples_engaged}"
    )
    if v.invariant_violations:
        print(f"[v1] invariant_violations ({len(v.invariant_violations)}):")
        for iv in v.invariant_violations:
            print(f"  - {iv.invariant_kind}: {iv.description}")
    if v.feedback is not None:
        print(
            f"[v1] last feedback: target_node={v.feedback.target_node.value}, "
            f"signature={v.feedback.blocking_signature}"
        )
    print(f"[v1] iteration_history (len={len(final.context.iterations)}):")
    for rec in final.context.iterations:
        print(
            f"  - iter={rec.iter_index} node={rec.node} "
            f"mode={rec.failure_mode.value} sig={rec.blocking_signature!r}"
        )


def _normalize_final_state(raw: object) -> V1State:
    """LangGraph invoke 반환은 dict 또는 V1State — 항상 V1State 로 변환."""
    if isinstance(raw, V1State):
        return raw
    return V1State.model_validate(raw)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint. exit code: 0 success, 1 fail."""
    load_dotenv()
    args = _build_parser().parse_args(argv)

    run_id = args.run_id or f"run-{uuid.uuid4().hex[:8]}"
    initial = initial_state(run_id, args.algorithm, max_iterations=args.max_iter)

    print(
        f"[v1] start run_id={run_id} algorithm={args.algorithm.value} "
        f"max_iter={args.max_iter}"
    )

    graph = build_graph()
    raw = graph.invoke(initial)
    final = _normalize_final_state(raw)

    _print_summary(final)
    if args.verbose:
        _print_verbose(final)

    if not args.no_output_dir:
        paths = persist_run_outputs(final, output_dir=args.output_dir)
        print(f"[v1] outputs persisted → {paths.run_dir}")

    return 0 if final.final_status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
