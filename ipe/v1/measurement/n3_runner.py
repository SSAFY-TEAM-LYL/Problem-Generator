"""N runs measurement runner for v1 graph (D안 PR-A5).

각 run 의 final V1State 를 ``RunOutcome`` dataclass 로 요약 → JSONL append +
summary 출력. PRINCIPLES.md 룰 1 (N≥3) 충족 + H1/H3 secondary signal
(samples_engaged 분포 + iteration depth) 추적.

PR-A5 gate (Dijkstra N=3):
- ≥ 2/3 success → Phase 2 진입 (LIS / SegmentTree verifier 확장)
- 1/3 → 회색지대, 추가 N=3 측정
- 0/3 → kill-switch 발동 (``ipe/v1/`` archive + retrospective)
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..graph import build_graph
from ..main_v1 import _normalize_final_state
from ..schema import TargetAlgorithm
from ..state import V1State, initial_state


@dataclass(frozen=True)
class RunOutcome:
    """한 run 의 요약 — JSONL 직렬화 단위. 디스크 raw 가 verifier 분석 anchor."""

    run_index: int
    run_id: str
    final_status: str | None
    iteration_used: int
    sample_pass_count: int
    sample_total: int
    samples_engaged: int
    invariant_violations: list[str]
    blocking_signatures: list[str]
    elapsed_seconds: float


GraphFactory = Callable[[], Any]


BASELINE_5_ALGORITHMS: tuple[TargetAlgorithm, ...] = (
    TargetAlgorithm.DIJKSTRA,
    TargetAlgorithm.LIS,
    TargetAlgorithm.SEGTREE,
    TargetAlgorithm.TWO_SUM,
    TargetAlgorithm.BFS,
)


PHASE_2B_13_ALGORITHMS: tuple[TargetAlgorithm, ...] = (
    TargetAlgorithm.DIJKSTRA,
    TargetAlgorithm.LIS,
    TargetAlgorithm.SEGTREE,
    TargetAlgorithm.TWO_SUM,
    TargetAlgorithm.BFS,
    TargetAlgorithm.BINARY_SEARCH,
    TargetAlgorithm.UNION_FIND,
    TargetAlgorithm.TOPOSORT,
    TargetAlgorithm.KNAPSACK,
    TargetAlgorithm.SORT,
    TargetAlgorithm.STRING_MATCH,
    TargetAlgorithm.MAX_FLOW,
    TargetAlgorithm.SIEVE,
)


def _summarize_state(idx: int, state: V1State, elapsed: float) -> RunOutcome:
    v = state.verification
    return RunOutcome(
        run_index=idx,
        run_id=state.run_id,
        final_status=state.final_status,
        iteration_used=state.iteration,
        sample_pass_count=sum(1 for sr in v.sample_results if sr.passed) if v else 0,
        sample_total=len(v.sample_results) if v else 0,
        samples_engaged=v.samples_engaged if v else 0,
        invariant_violations=(
            [iv.invariant_kind for iv in v.invariant_violations] if v else []
        ),
        blocking_signatures=[r.blocking_signature for r in state.context.iterations],
        elapsed_seconds=elapsed,
    )


def run_n_measurements(
    *,
    n: int,
    target_algorithm: TargetAlgorithm,
    max_iterations: int = 8,
    graph_factory: GraphFactory = build_graph,
    run_id_prefix: str = "v1-pr-a5",
) -> list[RunOutcome]:
    """N runs 실행, ``RunOutcome`` list 반환.

    ``graph_factory`` 주입 가능 — test 는 mock graph 사용해 cost 없이 검증.
    각 run 은 새 graph instance (state isolation).
    """
    if n <= 0:
        msg = f"n must be >= 1, got {n}"
        raise ValueError(msg)
    outcomes: list[RunOutcome] = []
    for i in range(n):
        run_id = f"{run_id_prefix}-{target_algorithm.value}-r{i + 1}"
        initial = initial_state(
            run_id, target_algorithm, max_iterations=max_iterations
        )
        start = time.time()
        try:
            graph = graph_factory()
            raw = graph.invoke(initial)
            final = _normalize_final_state(raw)
            elapsed = time.time() - start
            outcomes.append(_summarize_state(i, final, elapsed))
        except Exception as exc:  # noqa: BLE001
            elapsed = time.time() - start
            err_brief = f"{type(exc).__name__}: {exc!s}"[:200]
            print(
                f"[n3_runner] run r{i + 1} algo={target_algorithm.value} "
                f"raised {err_brief} — saving sentinel outcome"
            )
            outcomes.append(
                RunOutcome(
                    run_index=i,
                    run_id=run_id,
                    final_status="api_error",
                    iteration_used=0,
                    sample_pass_count=0,
                    sample_total=0,
                    samples_engaged=0,
                    invariant_violations=[],
                    blocking_signatures=[err_brief],
                    elapsed_seconds=elapsed,
                )
            )
    return outcomes


def write_jsonl(outcomes: list[RunOutcome], path: Path) -> None:
    """outcome list 를 JSONL 로 write. parent dir 자동 생성."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(o), ensure_ascii=False) for o in outcomes]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_phase_2b_measurements(
    *,
    n: int = 3,
    max_iterations: int = 8,
    graph_factory: GraphFactory = build_graph,
    run_id_prefix: str = "v1-pr-c8",
) -> list[RunOutcome]:
    """Phase 2b deliverable — 13 algo × N runs (default 39 runs).

    Baseline 5 + PR-C 시리즈 8 = 13 algorithm. Catalog ×2.6 확장의 anchor
    re-measurement. PR-B5 의 baseline 5 result 를 superset 으로 포함.
    """
    import dataclasses

    all_outcomes: list[RunOutcome] = []
    for algo in PHASE_2B_13_ALGORITHMS:
        algo_outcomes = run_n_measurements(
            n=n,
            target_algorithm=algo,
            max_iterations=max_iterations,
            graph_factory=graph_factory,
            run_id_prefix=f"{run_id_prefix}-{algo.value}",
        )
        for o in algo_outcomes:
            all_outcomes.append(
                dataclasses.replace(o, run_index=len(all_outcomes))
            )
    return all_outcomes


def run_baseline_5_measurements(
    *,
    n: int = 3,
    max_iterations: int = 8,
    graph_factory: GraphFactory = build_graph,
    run_id_prefix: str = "v1-pr-b5",
) -> list[RunOutcome]:
    """Phase 2a deliverable — baseline 5 algo × N runs (default 15 runs).

    각 algorithm 순회하며 ``run_n_measurements`` 호출. ``run_index`` 는 global
    sequence (0..N*5-1) 로 재정렬, ``run_id`` 는 algo-specific prefix 보존.

    PR-B5 Gate anchor: v0 baseline N=3 와 직접 비교 가능 (룰 2 cross-algorithm
    regression check).
    """
    import dataclasses

    all_outcomes: list[RunOutcome] = []
    for algo in BASELINE_5_ALGORITHMS:
        algo_outcomes = run_n_measurements(
            n=n,
            target_algorithm=algo,
            max_iterations=max_iterations,
            graph_factory=graph_factory,
            run_id_prefix=f"{run_id_prefix}-{algo.value}",
        )
        for o in algo_outcomes:
            all_outcomes.append(
                dataclasses.replace(o, run_index=len(all_outcomes))
            )
    return all_outcomes


def print_summary(outcomes: list[RunOutcome]) -> None:
    """run-level + sample-level + samples_engaged + per-run detail 출력."""
    n = len(outcomes)
    print(f"\n=== v1 N={n} measurement summary ===")
    success_count = sum(1 for o in outcomes if o.final_status == "success")
    print(f"run-level: {success_count}/{n} success")
    total_samples = sum(o.sample_total for o in outcomes)
    passed_samples = sum(o.sample_pass_count for o in outcomes)
    if total_samples:
        pct = passed_samples / total_samples * 100
        print(f"sample-level: {passed_samples}/{total_samples} ({pct:.1f}%)")
    engaged_total = sum(o.samples_engaged for o in outcomes)
    print(
        f"samples_engaged total: {engaged_total} (verifier 실효 검증, 0 == silent skip)"
    )
    print("per-run detail:")
    for o in outcomes:
        print(
            f"  r{o.run_index + 1}: status={o.final_status} iter={o.iteration_used} "
            f"samples={o.sample_pass_count}/{o.sample_total} "
            f"engaged={o.samples_engaged} elapsed={o.elapsed_seconds:.1f}s"
        )
        if o.invariant_violations:
            print(f"    violations: {o.invariant_violations}")
        if o.blocking_signatures:
            print(f"    blocking_sigs: {o.blocking_signatures}")
