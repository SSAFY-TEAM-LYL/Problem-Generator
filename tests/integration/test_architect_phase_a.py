"""Architect + Phase A 통합 테스트 (P4.5).

Architect/Coder의 LLM 호출을 ``monkeypatch``로 stub. Executor는 실제
``RlimitRunner``로 sandbox 실행. 시나리오:

1. happy path — graph 전체 사이클 → ``final_status == 'success'``
2. architect validator — missing field / too few samples / invalid constraints_structured
   각각 ``last_failed_node == 'architect'`` self-loop 시그널
3. Phase A 3-way 휴리스틱 — (a) 다수 통과 / (b) 전체 실패 + unique outputs
   둘 다 ``last_failed_node == 'architect'``로 라우팅 (REVIEW W3)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.graph import build_graph
from ipe.nodes import architect, coder, executor
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.state import ProblemState


def _make_tracker(tmp_path: Path) -> LLMCallTracker:
    return LLMCallTracker("test-run", tmp_path / "traces")


def _make_chat(content: str) -> MagicMock:
    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    chat.temperature = None
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": 0, "output_tokens": 0}
    chat.invoke.return_value = resp
    return chat


def _patch_chat(monkeypatch: pytest.MonkeyPatch, target: str, content: str) -> None:
    """``target``은 ``ipe.nodes.architect.get_chat`` 또는 ``ipe.nodes.coder.get_chat``."""
    monkeypatch.setattr(target, lambda *a, **k: _make_chat(content))


def _arch_response(samples: list[dict[str, Any]]) -> str:
    """Architect의 정상 응답 형식 — 펜스 안 JSON."""
    body = {
        "problem_title": "A+B",
        "problem_description": "Read two integers and print their sum.",
        "constraints": "1 <= a, b <= 1e9",
        "constraints_structured": {
            "variables": [
                {"name": "a", "min": 1, "max": 10**9, "type": "int"},
                {"name": "b", "min": 1, "max": 10**9, "type": "int"},
            ],
            "time_limit_ms": 2000,
            "memory_limit_mb": 256,
        },
        "sample_testcases": samples,
        "has_special_judge": False,
    }
    return f"```json\n{json.dumps(body)}\n```"


VALID_SAMPLES: list[dict[str, Any]] = [
    {"input": "1 2\n", "expected_output": "3"},
    {"input": "10 20\n", "expected_output": "30"},
    {"input": "5 7\n", "expected_output": "12"},
]
VALID_CODER = "```python\na, b = map(int, input().split())\nprint(a + b)\n```"


# =============================================================================
# 1. Happy path — 전체 graph 사이클
# =============================================================================


def test_happy_path_full_cycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """architect → coder → executor 1 cycle → final_status='success'."""
    _patch_chat(monkeypatch, "ipe.nodes.architect.get_chat", _arch_response(VALID_SAMPLES))
    _patch_chat(monkeypatch, "ipe.nodes.coder.get_chat", VALID_CODER)

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    state: ProblemState = {
        "target_algorithm": "A+B",
        "target_language": "python",
    }
    final = graph.invoke(state)

    assert final["final_status"] == "success"
    assert final["last_failed_node"] is None
    assert final["problem_title"] == "A+B"
    assert len(final["execution_results"]) == 3
    assert all(r["pass"] for r in final["execution_results"])


# =============================================================================
# 2. Architect validator — self-loop 시그널
# =============================================================================


class TestArchitectValidation:
    def test_missing_required_field(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """problem_description 누락 → architect self-loop."""
        bad = json.dumps({
            "problem_title": "X",
            "constraints": "...",
            "constraints_structured": {"time_limit_ms": 2000, "memory_limit_mb": 256},
            "sample_testcases": [
                {"input": "1\n", "expected_output": "1"},
                {"input": "2\n", "expected_output": "2"},
                {"input": "3\n", "expected_output": "3"},
            ],
        })
        _patch_chat(
            monkeypatch, "ipe.nodes.architect.get_chat", f"```json\n{bad}\n```"
        )

        state: ProblemState = {
            "target_algorithm": "X",
            "target_language": "python",
        }
        new_state = architect.run(state, tracker=_make_tracker(tmp_path))

        assert new_state["last_failed_node"] == "architect"
        feedback = new_state.get("feedback_message") or ""
        assert "missing fields" in feedback
        assert "problem_description" in feedback

    def test_too_few_samples(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """sample_testcases가 2개만 → self-loop (>=3 필요)."""
        bad = json.dumps({
            "problem_title": "X",
            "problem_description": "...",
            "constraints": "...",
            "constraints_structured": {"time_limit_ms": 2000, "memory_limit_mb": 256},
            "sample_testcases": [
                {"input": "1\n", "expected_output": "1"},
                {"input": "2\n", "expected_output": "2"},
            ],
        })
        _patch_chat(
            monkeypatch, "ipe.nodes.architect.get_chat", f"```json\n{bad}\n```"
        )

        state: ProblemState = {
            "target_algorithm": "X",
            "target_language": "python",
        }
        new_state = architect.run(state, tracker=_make_tracker(tmp_path))

        assert new_state["last_failed_node"] == "architect"
        assert "too few sample_testcases" in (new_state.get("feedback_message") or "")

    def test_invalid_constraints_structured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """constraints_structured.time_limit_ms 누락 → self-loop."""
        bad = json.dumps({
            "problem_title": "X",
            "problem_description": "...",
            "constraints": "...",
            "constraints_structured": {"memory_limit_mb": 256},
            "sample_testcases": [
                {"input": str(i), "expected_output": str(i)} for i in range(3)
            ],
        })
        _patch_chat(
            monkeypatch, "ipe.nodes.architect.get_chat", f"```json\n{bad}\n```"
        )

        state: ProblemState = {
            "target_algorithm": "X",
            "target_language": "python",
        }
        new_state = architect.run(state, tracker=_make_tracker(tmp_path))

        assert new_state["last_failed_node"] == "architect"
        feedback = new_state.get("feedback_message") or ""
        assert "constraints_structured" in feedback
        assert "time_limit_ms" in feedback


# =============================================================================
# 3. Phase A 3-way 휴리스틱 — REVIEW W3
# =============================================================================


class TestPhaseA3Way:
    def test_majority_pass_routes_to_architect(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """3 samples 중 2 통과 1 fail (no crash) → architect (3-way (a))."""
        wrong_samples: list[dict[str, Any]] = [
            {"input": "1 2\n", "expected_output": "3"},
            {"input": "10 20\n", "expected_output": "30"},
            {"input": "5 7\n", "expected_output": "999"},  # 잘못된 expected
        ]
        _patch_chat(
            monkeypatch,
            "ipe.nodes.architect.get_chat",
            _arch_response(wrong_samples),
        )
        _patch_chat(monkeypatch, "ipe.nodes.coder.get_chat", VALID_CODER)

        tracker = _make_tracker(tmp_path)
        state: ProblemState = {
            "target_algorithm": "A+B",
            "target_language": "python",
        }
        state = architect.run(state, tracker=tracker)
        state = coder.run(state, tracker=tracker)
        state = executor.run(
            state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
        )

        assert state["last_failed_node"] == "architect"
        feedback = state.get("feedback_message") or ""
        assert "expected_output likely wrong" in feedback

    def test_all_fail_unique_routes_to_architect(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """전체 실패 + 모든 출력이 unique → architect (3-way (b), W3 신규)."""
        wrong_samples: list[dict[str, Any]] = [
            {"input": "1 2\n", "expected_output": "WRONG_A"},
            {"input": "10 20\n", "expected_output": "WRONG_B"},
            {"input": "5 7\n", "expected_output": "WRONG_C"},
        ]
        _patch_chat(
            monkeypatch,
            "ipe.nodes.architect.get_chat",
            _arch_response(wrong_samples),
        )
        _patch_chat(monkeypatch, "ipe.nodes.coder.get_chat", VALID_CODER)

        tracker = _make_tracker(tmp_path)
        state: ProblemState = {
            "target_algorithm": "A+B",
            "target_language": "python",
        }
        state = architect.run(state, tracker=tracker)
        state = coder.run(state, tracker=tracker)
        state = executor.run(
            state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
        )

        assert state["last_failed_node"] == "architect"
        feedback = state.get("feedback_message") or ""
        assert "consistent unique outputs" in feedback
