"""n3_runner 단위 테스트 — mock graph factory (LLM 의존성 격리)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ipe.v1.measurement import (
    RunOutcome,
    print_summary,
    run_n_measurements,
    write_jsonl,
)
from ipe.v1.schema import (
    FailureMode,
    InvariantViolation,
    IterationContext,
    IterationRecord,
    SampleResult,
    StructuredFeedback,
    TargetAlgorithm,
    TargetNode,
    VerificationResult,
)
from ipe.v1.state import V1State


def _success_state(run_id: str) -> V1State:
    v = VerificationResult(
        overall_pass=True,
        failure_mode=FailureMode.NONE,
        iteration=0,
        sample_results=[
            SampleResult(
                index=i,
                passed=True,
                expected_output=str(i),
                actual_output=str(i),
                elapsed_ms=5,
            )
            for i in range(3)
        ],
        samples_engaged=3,
    )
    return V1State(
        run_id=run_id,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        iteration=1,
        verification=v,
        context=IterationContext(
            run_id=run_id, target_algorithm=TargetAlgorithm.DIJKSTRA
        ),
        final_status="success",
    )


def _budget_state(run_id: str) -> V1State:
    violation = InvariantViolation(
        invariant_kind="shortest_distance_optimal", description="x", evidence={}
    )
    v = VerificationResult(
        overall_pass=False,
        failure_mode=FailureMode.INVARIANT_VIOLATION,
        sample_results=[
            SampleResult(
                index=0,
                passed=False,
                expected_output="5",
                actual_output="10",
                elapsed_ms=5,
            ),
        ],
        invariant_violations=[violation],
        feedback=StructuredFeedback(
            target_node=TargetNode.CODER,
            actionable_hint="x",
            blocking_signature="shortest_distance_optimal-violated",
        ),
        iteration=7,
        samples_engaged=1,
    )
    ctx = IterationContext(
        run_id=run_id,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        iterations=[
            IterationRecord(
                iter_index=i,
                node="executor",
                failure_mode=FailureMode.INVARIANT_VIOLATION,
                blocking_signature=f"sig-{i}",
                timestamp_iso="2026-05-22T00:00:00Z",
            )
            for i in range(8)
        ],
    )
    return V1State(
        run_id=run_id,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        iteration=8,
        verification=v,
        context=ctx,
        final_status="fail_budget_exhausted",
    )


class _StubGraph:
    def __init__(self, final: V1State) -> None:
        self._final = final

    def invoke(self, initial: Any) -> V1State:
        return self._final.model_copy(update={"run_id": initial.run_id})


def _factory_for(states_by_index: list[V1State]) -> Any:
    counter = {"i": 0}

    def factory() -> _StubGraph:
        idx = counter["i"]
        counter["i"] += 1
        return _StubGraph(states_by_index[idx])

    return factory


# ---------- run_n_measurements ----------


def test_run_baseline_5_measurements_uses_all_algorithms_and_reindexes() -> None:
    """5 algo × N=2 = 10 runs. run_index 가 0..9 로 global reindex."""
    from ipe.v1.measurement.n3_runner import (
        BASELINE_5_ALGORITHMS,
        run_baseline_5_measurements,
    )

    # 5 algo × 2 = 10 stub states (모두 success).
    factory = _factory_for([_success_state(f"r{i}") for i in range(10)])
    outcomes = run_baseline_5_measurements(n=2, graph_factory=factory)

    assert len(outcomes) == 10
    assert [o.run_index for o in outcomes] == list(range(10))
    for i, algo in enumerate(BASELINE_5_ALGORITHMS):
        assert algo.value in outcomes[i * 2].run_id
        assert algo.value in outcomes[i * 2 + 1].run_id


def test_baseline_5_algorithms_constant_length() -> None:
    """baseline 5 = exactly 5 algorithms."""
    from ipe.v1.measurement.n3_runner import BASELINE_5_ALGORITHMS

    assert len(BASELINE_5_ALGORITHMS) == 5


def test_run_n_measurements_collects_outcomes_in_order() -> None:
    outcomes = run_n_measurements(
        n=3,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        graph_factory=_factory_for(
            [_success_state("a"), _budget_state("b"), _success_state("c")]
        ),
    )
    assert len(outcomes) == 3
    assert [o.run_index for o in outcomes] == [0, 1, 2]
    assert outcomes[0].final_status == "success"
    assert outcomes[1].final_status == "fail_budget_exhausted"
    assert outcomes[2].final_status == "success"


def test_run_n_measurements_run_id_prefix_used() -> None:
    outcomes = run_n_measurements(
        n=2,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        graph_factory=_factory_for([_success_state("x"), _success_state("y")]),
        run_id_prefix="custom-prefix",
    )
    assert outcomes[0].run_id == "custom-prefix-dijkstra-r1"
    assert outcomes[1].run_id == "custom-prefix-dijkstra-r2"


def test_run_n_measurements_rejects_zero_n() -> None:
    with pytest.raises(ValueError, match="n must be"):
        run_n_measurements(
            n=0,
            target_algorithm=TargetAlgorithm.DIJKSTRA,
            graph_factory=_factory_for([]),
        )


def test_run_outcome_captures_samples_engaged() -> None:
    outcomes = run_n_measurements(
        n=1,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        graph_factory=_factory_for([_success_state("x")]),
    )
    assert outcomes[0].samples_engaged == 3
    assert outcomes[0].sample_pass_count == 3
    assert outcomes[0].sample_total == 3


def test_run_outcome_captures_invariant_violations_and_sigs() -> None:
    outcomes = run_n_measurements(
        n=1,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        graph_factory=_factory_for([_budget_state("x")]),
    )
    assert outcomes[0].invariant_violations == ["shortest_distance_optimal"]
    assert len(outcomes[0].blocking_signatures) == 8


# ---------- write_jsonl ----------


def test_write_jsonl_round_trip(tmp_path: Path) -> None:
    outcomes = run_n_measurements(
        n=2,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        graph_factory=_factory_for([_success_state("x"), _budget_state("y")]),
    )
    out_path = tmp_path / "sub" / "data.jsonl"
    write_jsonl(outcomes, out_path)
    assert out_path.exists()
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["final_status"] == "success"
    assert parsed[1]["final_status"] == "fail_budget_exhausted"
    assert parsed[1]["samples_engaged"] == 1
    assert parsed[1]["invariant_violations"] == ["shortest_distance_optimal"]


def test_write_jsonl_creates_parent_dirs(tmp_path: Path) -> None:
    outcomes = run_n_measurements(
        n=1,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        graph_factory=_factory_for([_success_state("x")]),
    )
    out_path = tmp_path / "deeply" / "nested" / "dir" / "data.jsonl"
    write_jsonl(outcomes, out_path)
    assert out_path.exists()


# ---------- print_summary ----------


def test_print_summary_emits_run_level_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    outcomes = run_n_measurements(
        n=3,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        graph_factory=_factory_for(
            [_success_state("a"), _budget_state("b"), _success_state("c")]
        ),
    )
    print_summary(outcomes)
    captured = capsys.readouterr().out
    assert "run-level: 2/3 success" in captured
    assert "samples_engaged total" in captured
    assert "shortest_distance_optimal" in captured


def test_print_summary_no_violations_when_all_pass(
    capsys: pytest.CaptureFixture[str],
) -> None:
    outcomes = run_n_measurements(
        n=1,
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        graph_factory=_factory_for([_success_state("x")]),
    )
    print_summary(outcomes)
    captured = capsys.readouterr().out
    assert "run-level: 1/1 success" in captured
    assert "violations:" not in captured


# ---------- RunOutcome immutability ----------


def test_run_outcome_is_frozen_dataclass() -> None:
    o = RunOutcome(
        run_index=0,
        run_id="x",
        final_status="success",
        iteration_used=1,
        sample_pass_count=3,
        sample_total=3,
        samples_engaged=3,
        invariant_violations=[],
        blocking_signatures=[],
        elapsed_seconds=0.5,
    )
    with pytest.raises(AttributeError):
        o.run_index = 99  # type: ignore[misc]
