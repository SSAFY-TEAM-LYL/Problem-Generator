"""Replay 통합 테스트 (P8.5).

스펙: ARCHITECTURE.md §3.4, IMPLEMENTATION_ROADMAP §1 P8.5
범위: ``ReplayTracker``가 LLM 호출 0회로 cached trace를 재현.

mock helpers는 ``tests/integration/_helpers.py``로 통합 (P8 audit C1).

시나리오:
1. record + replay — 정상 run으로 traces 저장 → ReplayTracker로 재실행 →
   chat.invoke 호출 0건 + final_status='success' + 같은 testcases 산출
2. replay miss — traces가 비어있으면 ``RuntimeError("replay miss")``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from ipe.graph import build_graph
from ipe.observability import LLMCallTracker, ReplayTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from tests.integration._helpers import (
    initial_state,
    wire_all_chats_forbid_invoke,
    wire_all_chats_normal,
)


def test_replay_zero_llm_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """정상 run → traces 저장. 같은 traces로 ReplayTracker 사용 → chat.invoke 0회.

    Definition of Done: ``--replay <run_id>`` → LLM 호출 0회 발생.
    """
    traces_dir = tmp_path / "traces"
    db_record = tmp_path / "checkpoint_record.db"
    db_replay = tmp_path / "checkpoint_replay.db"
    runner = RlimitRunner()

    # ── 1단계: record (정상 LLM mock + LLMCallTracker)
    wire_all_chats_normal(monkeypatch)

    with SqliteSaver.from_conn_string(str(db_record)) as saver:
        tracker = LLMCallTracker("record-run", traces_dir)
        graph = build_graph(
            tracker=tracker, runner=runner,
            workdir_root=tmp_path / "wd_rec", checkpointer=saver,
        )
        config: dict[str, Any] = {
            "configurable": {"thread_id": "record"}, "recursion_limit": 60,
        }
        record_final = graph.invoke(initial_state(), config=config)

    assert record_final.get("final_status") == "success"
    trace_files = list(traces_dir.glob("*.json"))
    assert len(trace_files) >= 4, f"expected ≥4 traces, got {len(trace_files)}"

    # ── 2단계: replay (chat.invoke 호출 시 AssertionError + ReplayTracker)
    wire_all_chats_forbid_invoke(monkeypatch)

    with SqliteSaver.from_conn_string(str(db_replay)) as saver:
        replay_tracker = ReplayTracker("replay-run", traces_dir)
        graph = build_graph(
            tracker=replay_tracker, runner=runner,
            workdir_root=tmp_path / "wd_rep", checkpointer=saver,
        )
        config_replay: dict[str, Any] = {
            "configurable": {"thread_id": "replay"}, "recursion_limit": 60,
        }
        replay_final = graph.invoke(initial_state(), config=config_replay)

    # chat.invoke가 한 번도 호출되지 않은 상태여야 success까지 도달
    assert replay_final.get("final_status") == "success"
    # 기록된 LLM call 수가 record run과 일치해야 함
    assert len(replay_final.get("llm_calls") or []) == len(trace_files)


def test_replay_miss_raises_when_no_traces(tmp_path: Path) -> None:
    """traces_dir이 비어있으면 ReplayTracker.invoke가 첫 호출에서 즉시 raise."""
    empty_traces = tmp_path / "empty_traces"
    empty_traces.mkdir()
    tracker = ReplayTracker("empty-run", empty_traces)

    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    state_calls: list[Any] = []

    with pytest.raises(RuntimeError, match="replay miss"):
        tracker.invoke(chat, [], node="architect", state_calls=state_calls)
