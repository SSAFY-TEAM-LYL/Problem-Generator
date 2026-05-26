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
        graph = graph_factory()
        raw = graph.invoke(initial)
        final = _normalize_final_state(raw)
        elapsed = time.time() - start
        outcomes.append(_summarize_state(i, final, elapsed))
    return outcomes


def write_jsonl(outcomes: list[RunOutcome], path: Path) -> None:
    """outcome list 를 JSONL 로 write. parent dir 자동 생성."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(o), ensure_ascii=False) for o in outcomes]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
