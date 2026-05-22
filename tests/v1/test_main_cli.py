"""v1 CLI entrypoint 단위 테스트 — mock graph (LangChain 의존성 격리)."""

from __future__ import annotations

import argparse
from typing import Any

import pytest

from ipe.v1.main_v1 import (
    _build_parser,
    _normalize_final_state,
    _parse_target_algorithm,
    main,
)
from ipe.v1.schema import (
    FailureMode,
    TargetAlgorithm,
    VerificationResult,
)
from ipe.v1.state import V1State, initial_state

# ---------- _parse_target_algorithm ----------


def test_parse_target_algorithm_accepts_dijkstra_lowercase() -> None:
    assert _parse_target_algorithm("dijkstra") is TargetAlgorithm.DIJKSTRA


def test_parse_target_algorithm_accepts_dijkstra_uppercase() -> None:
    assert _parse_target_algorithm("DIJKSTRA") is TargetAlgorithm.DIJKSTRA


def test_parse_target_algorithm_rejects_unsupported() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="unsupported algorithm"):
        _parse_target_algorithm("bfs")


# ---------- _build_parser ----------


def test_parser_requires_algorithm() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_parses_minimal_args() -> None:
    parser = _build_parser()
    ns = parser.parse_args(["--algorithm", "dijkstra"])
    assert ns.algorithm is TargetAlgorithm.DIJKSTRA
    assert ns.run_id is None
    assert ns.max_iter == 8


def test_parser_parses_all_args() -> None:
    parser = _build_parser()
    ns = parser.parse_args(
        ["--algorithm", "dijkstra", "--run-id", "my-run", "--max-iter", "4"]
    )
    assert ns.run_id == "my-run"
    assert ns.max_iter == 4


# ---------- _normalize_final_state ----------


def test_normalize_passes_v1state_through() -> None:
    state = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    assert _normalize_final_state(state) is state


def test_normalize_validates_from_dict() -> None:
    state = initial_state("r1", TargetAlgorithm.DIJKSTRA)
    raw = state.model_dump()
    normalized = _normalize_final_state(raw)
    assert isinstance(normalized, V1State)
    assert normalized.run_id == "r1"


# ---------- main() ----------


class _StubGraph:
    """build_graph() 의 mock — invoke 가 정해진 final state 반환."""

    def __init__(self, final: V1State) -> None:
        self._final = final
        self.invoke_calls: list[Any] = []

    def invoke(self, initial: Any) -> V1State:
        self.invoke_calls.append(initial)
        return self._final


def _success_state(run_id: str = "test") -> V1State:
    base = initial_state(run_id, TargetAlgorithm.DIJKSTRA)
    v = VerificationResult(
        overall_pass=True,
        failure_mode=FailureMode.NONE,
        iteration=0,
        samples_engaged=3,
    )
    return base.model_copy(update={"verification": v, "final_status": "success"})


def _budget_state(run_id: str = "test") -> V1State:
    base = initial_state(run_id, TargetAlgorithm.DIJKSTRA)
    return base.model_copy(update={"final_status": "fail_budget_exhausted"})


def test_main_returns_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubGraph(_success_state())
    monkeypatch.setattr("ipe.v1.main_v1.build_graph", lambda: stub)
    code = main(["--algorithm", "dijkstra", "--run-id", "test-success"])
    assert code == 0
    assert len(stub.invoke_calls) == 1


def test_main_returns_one_on_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubGraph(_budget_state())
    monkeypatch.setattr("ipe.v1.main_v1.build_graph", lambda: stub)
    code = main(["--algorithm", "dijkstra", "--run-id", "test-budget"])
    assert code == 1


def test_main_generates_random_run_id_when_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _StubGraph(_success_state())
    monkeypatch.setattr("ipe.v1.main_v1.build_graph", lambda: stub)
    main(["--algorithm", "dijkstra"])
    initial = stub.invoke_calls[0]
    assert isinstance(initial, V1State)
    assert initial.run_id.startswith("run-")
    assert len(initial.run_id) > len("run-")


def test_main_respects_max_iter_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubGraph(_success_state())
    monkeypatch.setattr("ipe.v1.main_v1.build_graph", lambda: stub)
    main(["--algorithm", "dijkstra", "--max-iter", "3"])
    initial = stub.invoke_calls[0]
    assert isinstance(initial, V1State)
    assert initial.max_iterations == 3
