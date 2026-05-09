"""Evaluator 통합 테스트 (P9.4).

스펙: ARCHITECTURE.md §3.10, IMPLEMENTATION_ROADMAP §1 P9.4
범위: graph.invoke happy path → evaluator → difficulty_* 4 필드 + reasoning에
anchor id 명시.

mock helpers는 ``tests/integration/_helpers.py`` (P8 audit C1) 사용.

시나리오:
1. happy path full cycle → success + difficulty_label/reasoning/factors/anchors 채워짐 +
   reasoning에 anchor id 인용
2. evaluator parse 실패 (malformed JSON) → success는 보존, difficulty_* 미설정
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ipe.graph import build_graph
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from tests.integration._helpers import (
    initial_state,
    patch_chat,
    wire_all_chats_normal,
)


def _make_tracker(tmp_path: Path) -> LLMCallTracker:
    return LLMCallTracker("test-evaluator", tmp_path / "traces")


def test_evaluator_populates_difficulty_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """happy path → final_status='success' + difficulty_* 4 필드 채워짐 + anchor id 인용."""
    wire_all_chats_normal(monkeypatch)

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    final = graph.invoke(initial_state())

    assert final.get("final_status") == "success"
    assert final.get("last_failed_node") is None

    # 4 difficulty 필드 모두 채워졌어야 함
    assert final.get("difficulty_label") == "Bronze V"
    reasoning = final.get("difficulty_reasoning") or ""
    assert "bj_1000_bronze5" in reasoning, f"reasoning should cite anchor id: {reasoning!r}"

    factors = final.get("difficulty_factors") or {}
    assert factors.get("algorithm") == "implementation"
    assert factors.get("complexity") == "O(1)"

    # used anchors가 dict entries로 매칭됨 (id → label/summary/factors)
    used = final.get("difficulty_calibration_anchors") or []
    assert len(used) == 1
    assert used[0].get("id") == "bj_1000_bronze5"
    assert used[0].get("label") == "Bronze V"


def test_evaluator_parse_failure_preserves_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """evaluator가 malformed 응답을 반환해도 final_status='success' 보존, difficulty_* 미설정."""
    wire_all_chats_normal(monkeypatch)
    # evaluator만 malformed JSON으로 override
    patch_chat(monkeypatch, "ipe.nodes.evaluator.get_chat", "not a json block at all")

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    final = graph.invoke(initial_state())

    # success는 보존
    assert final.get("final_status") == "success"
    # difficulty_* 미설정 (None)
    assert final.get("difficulty_label") is None
    assert final.get("difficulty_reasoning") is None
    assert final.get("difficulty_factors") is None
    # calibration_anchors도 미설정 (None or 빈 list 허용)
    used = final.get("difficulty_calibration_anchors")
    assert used is None or used == []
