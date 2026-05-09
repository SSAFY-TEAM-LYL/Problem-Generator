"""auditor.py 단위 테스트 (polish round 2 — B3 해소).

스펙: PROJECT_SPEC.md §4.3, IMPLEMENTATION_ROADMAP §1 P5
범위: ``_normalize_entry`` + ``_route_back`` + run의 fallback 분기
(JSON list / truncation 복구).

기존 통합 테스트 (``tests/integration/test_phase_b.py``)는 happy/major paths만
cover — 본 단위 테스트가 edge cases 보강.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.nodes.auditor import (
    _normalize_entry,
    _route_back,
)
from ipe.nodes.auditor import run as auditor_run
from ipe.observability import LLMCallTracker
from ipe.state import ProblemState

# =============================================================================
# _normalize_entry — non-dict / missing input / 정상화
# =============================================================================


class TestNormalizeEntry:
    def test_non_dict_returns_none(self) -> None:
        """list 안에 string entry → None (line 97)."""
        assert _normalize_entry("not a dict") is None
        assert _normalize_entry(42) is None
        assert _normalize_entry([]) is None

    def test_missing_input_returns_none(self) -> None:
        """input 키 누락 → None (line 99)."""
        assert _normalize_entry({"category": "MIN"}) is None
        assert _normalize_entry({}) is None

    def test_minimal_valid_entry(self) -> None:
        """input만 있어도 default category/reason으로 정상화."""
        out = _normalize_entry({"input": "1 2"})
        assert out is not None
        assert out["input"] == "1 2"
        assert out["category"] == "ADVERSARIAL"  # default
        assert out["reason"] == ""

    def test_full_entry_preserved(self) -> None:
        out = _normalize_entry({
            "input": "5 5",
            "category": "BOUNDARY_HIGH",
            "reason": "max value",
        })
        assert out == {
            "input": "5 5",
            "category": "BOUNDARY_HIGH",
            "reason": "max value",
        }

    def test_input_coerced_to_str(self) -> None:
        """input이 int/list 등이면 str(...)로 변환."""
        out = _normalize_entry({"input": 42})
        assert out is not None
        assert out["input"] == "42"


# =============================================================================
# _route_back — auditor self-loop
# =============================================================================


class TestRouteBack:
    def test_basic_route_back(self) -> None:
        state: ProblemState = {"problem_title": "Two Sum"}
        result = _route_back(state, [], "only 5 valid cases, need >= 8")
        assert result["last_failed_node"] == "auditor"
        assert "5 valid cases" in (result.get("feedback_message") or "")
        assert result["problem_title"] == "Two Sum"


# =============================================================================
# run() fallback 분기 — JSON list (line 139-140) + truncation (141-143)
# =============================================================================


def _make_chat_returning(content: str) -> MagicMock:
    """auditor.get_chat가 반환하는 chat mock — invoke가 content 응답 반환."""
    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": 0, "output_tokens": 0}
    chat.invoke.return_value = resp
    return chat


def _patch_chat(monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    monkeypatch.setattr(
        "ipe.nodes.auditor.get_chat", lambda *a, **k: _make_chat_returning(content)
    )


def _make_state() -> ProblemState:
    return {
        "problem_description": "A+B",
        "constraints": "1 <= a, b <= 1e9",
        "solution_code": "print(sum(map(int, input().split())))",
        "target_language": "python",
    }


class TestRunFallbacks:
    def test_top_level_list_response_accepted(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """data가 list 자체면 inputs로 사용 (line 139-140)."""
        # 8 valid entries — list 직접 (envelope 없음)
        cases = [
            {"input": f"{i} {i}", "category": "MIN"} for i in range(8)
        ]
        _patch_chat(monkeypatch, f"```json\n{json.dumps(cases)}\n```")

        tracker = LLMCallTracker("test", tmp_path / "traces")
        new_state = auditor_run(_make_state(), tracker=tracker)

        # 8 cases가 정상 정규화되어 adversarial_inputs에 set
        assert "adversarial_inputs" in new_state
        assert len(new_state["adversarial_inputs"]) == 8
        # last_failed_node None (정상 통과)
        assert new_state.get("last_failed_node") is None

    def test_truncated_json_recovers_complete_entries(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """parse_json_block ValueError → parse_json_array_field로 truncation 복구
        (line 141-143)."""
        # max_tokens에 걸려 truncated된 응답 — 8 완전 entries + 9번째 부분 entry
        complete_entries = [
            {"input": f"{i} {i}", "category": "MIN", "reason": "small"}
            for i in range(8)
        ]
        # 일부러 trailing comma + 미완성 entry 추가 → JSON parse 실패 유도
        truncated = (
            '{"adversarial_inputs": ['
            + ",".join(json.dumps(e) for e in complete_entries)
            + ', {"input": "abc'   # 미완성 — 닫는 } 없음
        )
        _patch_chat(monkeypatch, truncated)

        tracker = LLMCallTracker("test", tmp_path / "traces")
        new_state = auditor_run(_make_state(), tracker=tracker)

        # parse_json_array_field가 완성된 8 entries만 복구
        assert "adversarial_inputs" in new_state
        assert len(new_state["adversarial_inputs"]) == 8

    def test_too_few_cases_routes_back(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """5 entries만 반환 → MIN_ADVERSARIAL_CASES(8) 미달 → self-loop."""
        few = [{"input": f"{i}", "category": "MIN"} for i in range(5)]
        _patch_chat(
            monkeypatch,
            f"```json\n{json.dumps({'adversarial_inputs': few})}\n```",
        )

        tracker = LLMCallTracker("test", tmp_path / "traces")
        new_state = auditor_run(_make_state(), tracker=tracker)

        assert new_state["last_failed_node"] == "auditor"
        feedback = new_state.get("feedback_message") or ""
        assert "5" in feedback or "valid" in feedback
