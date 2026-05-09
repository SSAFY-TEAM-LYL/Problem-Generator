"""Resume 통합 테스트 (P8.5).

스펙: ARCHITECTURE.md §3.4, IMPLEMENTATION_ROADMAP §1 P8.5
범위: SqliteSaver 영속화 + 의도적 abort + ``graph.invoke(None, config)`` 재개.

mock helpers는 ``tests/integration/_helpers.py``로 통합 (P8 audit C1).

시나리오:
1. checkpoint.db 자동 생성 — happy path 1회 invoke 후 db 파일 존재
2. abort + resume — 첫 invoke에서 coder가 raise → 같은 thread_id로 다시 invoke(None) →
   architect 결과는 보존된 채 coder부터 재실행 → success
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from ipe.graph import build_graph
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from tests.integration._helpers import (
    VALID_SAMPLES,
    arch_response,
    initial_state,
    patch_chat,
    patch_chat_raises,
    wire_all_chats_normal,
)


def test_checkpoint_db_created_on_invoke(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SqliteSaver context로 graph.invoke 1회 → db 파일 생성됨."""
    wire_all_chats_normal(monkeypatch)
    db_path = tmp_path / "checkpoint.db"
    traces_dir = tmp_path / "traces"
    runner = RlimitRunner()

    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        tracker = LLMCallTracker("run1", traces_dir)
        graph = build_graph(
            tracker=tracker, runner=runner,
            workdir_root=tmp_path / "wd", checkpointer=saver,
        )
        config: dict[str, Any] = {
            "configurable": {"thread_id": "run1"}, "recursion_limit": 60,
        }
        final = graph.invoke(initial_state(), config=config)

    assert db_path.exists()
    assert db_path.stat().st_size > 0
    assert final.get("final_status") == "success"


def test_resume_after_coder_abort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """첫 invoke에서 coder가 raise → checkpoint.db에 architect 결과까지 저장 →
    같은 thread_id로 invoke(None) → coder부터 재실행 → success.
    """
    db_path = tmp_path / "checkpoint.db"
    traces_dir = tmp_path / "traces"
    runner = RlimitRunner()
    thread_id = "resume-thread"

    # 1단계: architect 정상, coder가 raise → 의도적 abort
    patch_chat(monkeypatch, "ipe.nodes.architect.get_chat", arch_response(VALID_SAMPLES))
    patch_chat_raises(
        monkeypatch, "ipe.nodes.coder.get_chat",
        RuntimeError("simulated network error"),
    )

    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        tracker = LLMCallTracker("run1", traces_dir)
        graph = build_graph(
            tracker=tracker, runner=runner,
            workdir_root=tmp_path / "wd", checkpointer=saver,
        )
        config: dict[str, Any] = {
            "configurable": {"thread_id": thread_id}, "recursion_limit": 60,
        }
        with pytest.raises(RuntimeError, match="simulated network error"):
            graph.invoke(initial_state(), config=config)

    # checkpoint.db에 architect 결과가 저장되어 있어야 함
    assert db_path.exists()

    # 2단계: 같은 thread_id로 resume — 모든 mock 정상
    wire_all_chats_normal(monkeypatch)

    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        tracker = LLMCallTracker("run1", traces_dir)
        graph = build_graph(
            tracker=tracker, runner=runner,
            workdir_root=tmp_path / "wd", checkpointer=saver,
        )
        config_resume: dict[str, Any] = {
            "configurable": {"thread_id": thread_id}, "recursion_limit": 60,
        }
        final = graph.invoke(None, config=config_resume)

    assert final.get("final_status") == "success"
    # architect의 산출물이 보존되어야 함 (재호출 없이)
    assert final.get("problem_title") == "A+B"
