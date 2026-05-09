"""Routing 통합 테스트 — graph.invoke full cycle (P7.4).

스펙: ARCHITECTURE.md §3.4, IMPLEMENTATION_ROADMAP §1 P7.4
범위: graph.invoke를 통한 의도적 실패 사이클 — Definition of Done 4종.

단위 테스트 (``_decision``, ``_route_after_decision``, ``build_history_section``)
는 ``tests/test_routing_units.py``로 분리 (P7 audit B1, budget ≤400 준수).
mock helpers는 ``tests/integration/_helpers.py``로 통합 (P8 audit C1).

시나리오:
1. happy path full cycle → ``final_status='success'`` + sample/adv/generated testcases
2. coder budget exhausted (BAD_CODER + budget=2) → ``budget_exhausted``
3. max_iter=1 + 잘못된 코드 → ``max_iterations``
4. max_cost_usd=0.01 + 10k tokens → ``cost_exceeded``
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ipe.graph import build_graph
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from tests.integration._helpers import (
    BAD_CODER,
    default_budget,
    initial_state,
    wire_all_chats_normal,
)


def _make_tracker(tmp_path: Path) -> LLMCallTracker:
    return LLMCallTracker("test-routing", tmp_path / "traces")


def test_happy_path_full_cycle_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """architect+coder+auditor+generator 모두 정상 mock → graph.invoke → success."""
    wire_all_chats_normal(monkeypatch)

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    final = graph.invoke(initial_state())
    assert final.get("final_status") == "success", (
        f"got {final.get('final_status')} "
        f"(failed={final.get('last_failed_node')}: {final.get('feedback_message')!r})"
    )
    assert final.get("last_failed_node") is None
    testcases = final.get("testcases") or []
    assert any(t.get("kind") == "sample" for t in testcases)
    assert any(t.get("kind") == "adversarial" for t in testcases)
    assert any(t.get("kind") == "generated" for t in testcases)


def test_coder_budget_exhausted_halt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """잘못된 코드(print(0)) 반복 → coder 라우팅 누적 → budget_exhausted halt.

    coder budget=2로 설정 → 2회 retry 후 3번째 fail에서 budget_exhausted.
    """
    wire_all_chats_normal(monkeypatch, coder_response=BAD_CODER)

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    budget = default_budget()
    budget["coder"] = 2
    final = graph.invoke(initial_state(budget=budget))

    assert final.get("final_status") == "budget_exhausted"
    assert "coder" in (final.get("feedback_message") or "")
    # iteration_history에 coder 시도가 누적되었어야 함
    history = final.get("iteration_history") or []
    coder_entries = [h for h in history if h.get("node") == "coder"]
    assert len(coder_entries) >= 2


def test_max_iter_halt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """max_iter=1 + 잘못된 코드 → 1 cycle 후 max_iterations halt."""
    wire_all_chats_normal(monkeypatch, coder_response=BAD_CODER)

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    final = graph.invoke(initial_state(max_iter=1))
    assert final.get("final_status") == "max_iterations"
    assert final.get("iteration_count") == 1


def test_cost_exceeded_halt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """큰 토큰 사용 + max_cost_usd=0.01 → 첫 cycle에서 cost_exceeded.

    Opus pricing: 10k in + 10k out → ($0.15 + $0.75) = $0.90 per call.
    architect 1 call만 호출되어도 max=$0.01 초과 — decision에서 즉시 halt.
    """
    wire_all_chats_normal(monkeypatch, coder_response=BAD_CODER, in_tok=10000, out_tok=10000)

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    final = graph.invoke(initial_state(max_cost_usd=0.01))
    assert final.get("final_status") == "cost_exceeded"
    feedback = final.get("feedback_message") or ""
    assert "cost guard" in feedback
