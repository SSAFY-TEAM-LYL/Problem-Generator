"""Minimal-circuit integration test — Coder + Executor round-trip.

Coder의 LLM 호출은 ``monkeypatch``로 ``get_chat``을 stub. Executor는 실제
``RlimitRunner``로 sandbox 실행. ``A+B`` problem 기준으로 4 시나리오 검증:
1. happy path → ``final_status == 'success'``
2. IMPOSSIBLE → ``last_failed_node == 'architect'``
3. wrong output → Phase A failure → ``last_failed_node == 'coder'``
4. syntax error → 런타임 RTE → ``last_failed_node == 'coder'``
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.nodes import coder, executor
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.state import ProblemState


def _make_tracker(tmp_path: Path) -> LLMCallTracker:
    """tracker 헬퍼 — production path와 동일한 회계를 활성화."""
    return LLMCallTracker("test-run", tmp_path / "traces")


def _make_mock_chat(content: str) -> MagicMock:
    """Coder가 부르는 chat을 mock — 고정 응답 반환."""
    chat = MagicMock()
    chat.model = "claude-sonnet-4-6"
    chat.temperature = 0.7
    mock_resp = MagicMock(spec=BaseMessage)
    mock_resp.content = content
    mock_resp.usage_metadata = {"input_tokens": 0, "output_tokens": 0}
    chat.invoke.return_value = mock_resp
    return chat


def _patch_coder_chat(monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    monkeypatch.setattr(
        "ipe.nodes.coder.get_chat",
        lambda *a, **k: _make_mock_chat(content),
    )


def test_phase_a_pass_routes_to_auditor_when_no_adversarial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A+B 정해 → Phase A 통과 → adversarial 부재 → auditor 라우팅 (P5.3).

    P5에서 Phase B가 추가됨에 따라 Phase A 통과만으로는 success 아님 —
    adversarial_inputs가 채워져야 success. happy path 검증은 Phase B
    통합 테스트(``test_phase_b.py``)에서 별도로 다룬다.
    """
    fake = "```python\na, b = map(int, input().split())\nprint(a + b)\n```"
    _patch_coder_chat(monkeypatch, fake)
    tracker = _make_tracker(tmp_path)

    state: ProblemState = {
        "target_algorithm": "Two Sum",
        "target_language": "python",
        "problem_description": "두 수 A와 B를 입력받아 A+B를 출력하라.",
        "constraints": "1 <= A, B <= 1e9",
        "sample_testcases": [
            {"input": "1 2\n", "expected_output": "3"},
            {"input": "10 20\n", "expected_output": "30"},
        ],
    }

    # 1) Coder
    state = coder.run(state, tracker=tracker)
    assert "solution_code" in state
    assert "a + b" in state["solution_code"]

    # 2) Executor (Phase A 통과 → adversarial 부재 → auditor)
    state = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    # 3) 검증 — Phase A는 통과 + auditor로 라우팅
    assert state.get("final_status") is None
    assert state["last_failed_node"] == "auditor"
    feedback = state.get("feedback_message") or ""
    assert "no adversarial_inputs" in feedback
    results = state["execution_results"]
    assert len(results) == 2
    assert all(r["pass"] for r in results)


def test_impossible_routes_to_architect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``IMPOSSIBLE: <reason>``이 펜스 앞에 있으면 architect로."""
    fake = "IMPOSSIBLE: contradictory constraints\n```python\npass\n```"
    _patch_coder_chat(monkeypatch, fake)
    tracker = _make_tracker(tmp_path)

    state: ProblemState = {
        "target_language": "python",
        "problem_description": "x",
        "constraints": "x",
    }
    state = coder.run(state, tracker=tracker)

    assert state["last_failed_node"] == "architect"
    feedback = state.get("feedback_message") or ""
    assert "IMPOSSIBLE" in feedback
    assert "contradictory" in feedback


def test_wrong_output_routes_to_coder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """항상 0을 출력하는 오답 솔루션 → Phase A failure → coder."""
    fake = "```python\nprint(0)\n```"
    _patch_coder_chat(monkeypatch, fake)
    tracker = _make_tracker(tmp_path)

    state: ProblemState = {
        "target_language": "python",
        "problem_description": "x",
        "constraints": "x",
        "sample_testcases": [{"input": "1 2\n", "expected_output": "3"}],
    }
    state = coder.run(state, tracker=tracker)
    state = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    assert state.get("final_status") is None  # success set 안 됨
    assert state["last_failed_node"] == "coder"
    assert "phase A failures" in (state.get("feedback_message") or "")


def test_syntax_error_routes_to_coder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """python syntax error → 런타임 RTE → Phase A failure → coder."""
    fake = "```python\nthis is not python(\n```"
    _patch_coder_chat(monkeypatch, fake)
    tracker = _make_tracker(tmp_path)

    state: ProblemState = {
        "target_language": "python",
        "problem_description": "x",
        "constraints": "x",
        "sample_testcases": [{"input": "1\n", "expected_output": "1"}],
    }
    state = coder.run(state, tracker=tracker)
    state = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    # Python은 _compile에서 no-op이므로 컴파일 OK
    # 런타임에 SyntaxError 발생 → RTE → Phase A failure
    assert state["last_failed_node"] == "coder"
    results = state["execution_results"]
    assert results[0]["status"] == "RTE"
    assert results[0]["pass"] is False
