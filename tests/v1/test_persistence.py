"""persistence.py 단위 테스트 — outputs/<run_id>/ dump 검증."""

from __future__ import annotations

import json
from pathlib import Path

from ipe.v1.persistence import persist_run_outputs
from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    Invariant,
    IOContract,
    ProblemSpec,
    SampleResult,
    SampleTestCase,
    SolutionAttempt,
    TargetAlgorithm,
    VerificationResult,
)
from ipe.v1.schema import FailureMode
from ipe.v1.state import initial_state


def _spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="shortest path s->t",
        description="V vertices, E edges; output d[s][t] or -1.",
        io_contract=IOContract(input_format="V E s t...", output_format="int"),
        sample_testcases=[
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
            SampleTestCase(input_text="3 2 0 2\n0 1 1\n1 2 2", expected_output="3"),
            SampleTestCase(input_text="2 0 0 1", expected_output="-1"),
        ],
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Dijkstra",
        complexity_target=ComplexityBound(
            time_big_o="O((V+E) log V)", space_big_o="O(V+E)"
        ),
        pseudocode="dist[s]=0; pq; relax.",
        invariants=[
            Invariant(
                kind="non_negative_distance", description="모든 결과 >= 0"
            )
        ],
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="print(5)\n", iteration=0)


def _verification() -> VerificationResult:
    return VerificationResult(
        overall_pass=True,
        failure_mode=FailureMode.NONE,
        sample_results=[
            SampleResult(
                index=0,
                passed=True,
                expected_output="5",
                actual_output="5",
                stderr="",
                elapsed_ms=10,
            ),
        ],
        invariant_violations=[],
        feedback=None,
        iteration=0,
        samples_engaged=1,
    )


def test_persist_all_fields_creates_5_files(tmp_path: Path) -> None:
    state = initial_state("run-test-001", TargetAlgorithm.DIJKSTRA).model_copy(
        update={
            "spec": _spec(),
            "design": _design(),
            "attempt": _attempt(),
            "verification": _verification(),
            "final_status": "success",
        }
    )
    paths = persist_run_outputs(state, output_dir=tmp_path)
    assert paths.run_dir == (tmp_path / "run-test-001").resolve()
    assert paths.spec_json is not None and paths.spec_json.exists()
    assert paths.design_json is not None and paths.design_json.exists()
    assert paths.attempt_py is not None and paths.attempt_py.exists()
    assert paths.verification_json is not None and paths.verification_json.exists()
    assert paths.outcome_json.exists()


def test_persist_spec_json_parseable(tmp_path: Path) -> None:
    state = initial_state("run-spec-only", TargetAlgorithm.DIJKSTRA).model_copy(
        update={"spec": _spec()}
    )
    paths = persist_run_outputs(state, output_dir=tmp_path)
    assert paths.spec_json is not None
    data = json.loads(paths.spec_json.read_text())
    assert data["title"] == "shortest path s->t"
    assert data["target_algorithm"] == "dijkstra"
    assert len(data["sample_testcases"]) == 3


def test_persist_attempt_py_is_raw_code(tmp_path: Path) -> None:
    state = initial_state("run-attempt", TargetAlgorithm.DIJKSTRA).model_copy(
        update={"attempt": _attempt()}
    )
    paths = persist_run_outputs(state, output_dir=tmp_path)
    assert paths.attempt_py is not None
    assert paths.attempt_py.read_text() == "print(5)\n"


def test_persist_skip_none_fields(tmp_path: Path) -> None:
    """spec/design/attempt 가 None 이면 file 생성 skip."""
    state = initial_state("run-empty", TargetAlgorithm.DIJKSTRA)
    paths = persist_run_outputs(state, output_dir=tmp_path)
    assert paths.spec_json is None
    assert paths.design_json is None
    assert paths.attempt_py is None
    assert paths.verification_json is None
    assert paths.outcome_json.exists()


def test_outcome_summary_includes_metric_fields(tmp_path: Path) -> None:
    state = initial_state("run-outcome", TargetAlgorithm.DIJKSTRA).model_copy(
        update={
            "spec": _spec(),
            "verification": _verification(),
            "final_status": "success",
        }
    )
    paths = persist_run_outputs(state, output_dir=tmp_path)
    data = json.loads(paths.outcome_json.read_text())
    assert data["run_id"] == "run-outcome"
    assert data["target_algorithm"] == "dijkstra"
    assert data["final_status"] == "success"
    assert data["sample_pass_count"] == 1
    assert data["sample_total"] == 1
    assert data["samples_engaged"] == 1


def test_persist_creates_run_dir_if_missing(tmp_path: Path) -> None:
    output_dir = tmp_path / "nested" / "outputs"
    state = initial_state("run-mkdir", TargetAlgorithm.DIJKSTRA)
    paths = persist_run_outputs(state, output_dir=output_dir)
    assert paths.run_dir.exists()
    assert paths.run_dir.is_dir()


def test_persist_str_path_accepted(tmp_path: Path) -> None:
    state = initial_state("run-strpath", TargetAlgorithm.DIJKSTRA)
    paths = persist_run_outputs(state, output_dir=str(tmp_path))
    assert paths.run_dir.exists()


def test_persist_overwrite_existing_run_dir(tmp_path: Path) -> None:
    """동일 run_id 다시 persist → 덮어쓰기 (re-run 지원)."""
    state1 = initial_state("run-rerun", TargetAlgorithm.DIJKSTRA).model_copy(
        update={"attempt": SolutionAttempt(code="print(1)", iteration=0)}
    )
    paths1 = persist_run_outputs(state1, output_dir=tmp_path)
    assert paths1.attempt_py is not None
    assert paths1.attempt_py.read_text() == "print(1)"

    state2 = initial_state("run-rerun", TargetAlgorithm.DIJKSTRA).model_copy(
        update={"attempt": SolutionAttempt(code="print(2)", iteration=0)}
    )
    paths2 = persist_run_outputs(state2, output_dir=tmp_path)
    assert paths2.attempt_py is not None
    assert paths2.attempt_py.read_text() == "print(2)"
