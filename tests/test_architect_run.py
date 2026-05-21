"""architect.py 단위 테스트 — `_parse_and_validate` + `run` (single Opus call).

v0.3.0-rc1 M3 rollback (2026-05-21) 후 — dual-call consensus 제거. 본 파일은
기존 `test_architect_consensus.py` 의 후속이며, 다음 테스트들 유지:
- ``TestParseAndValidate``: helper 검증 (single call에서도 동일하게 사용됨)
- ``TestRunArchitect``: single Opus call success / parse failure / route_back

기존 M3 specific 테스트 (``TestStructuralMatch``, ``TestSummarize``,
``TestRunConsensus``, ``TestM3Disabled``) 는 제거 — 해당 helper / dual-call
코드가 모두 제거됨.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.nodes.architect import _parse_and_validate, run
from ipe.observability import LLMCallTracker
from ipe.state import ProblemState


def _make_tracker(tmp_path: Path) -> LLMCallTracker:
    return LLMCallTracker("test-run", tmp_path / "traces")


def _make_chat(content: str, model: str = "claude-opus-4-7") -> MagicMock:
    chat = MagicMock()
    chat.model = model
    chat.temperature = None
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": 0, "output_tokens": 0}
    chat.invoke.return_value = resp
    return chat


def _arch_body(
    *,
    title: str = "A+B",
    time_ms: int = 2000,
    mem_mb: int = 256,
    var_names: tuple[str, ...] = ("a", "b"),
    n_samples: int = 3,
) -> dict[str, Any]:
    """architect 정상 응답 dict — 테스트마다 구조 파라미터 조정 가능."""
    return {
        "problem_title": title,
        "problem_description": f"Description for {title}",
        "constraints": f"1 ≤ {var_names[0]} ≤ 1e9",
        "constraints_structured": {
            "variables": [
                {"name": name, "min": 1, "max": 10**9, "type": "int"}
                for name in var_names
            ],
            "time_limit_ms": time_ms,
            "memory_limit_mb": mem_mb,
        },
        "sample_testcases": [
            {"input": f"{i}\n", "expected_output": str(i)} for i in range(n_samples)
        ],
        "has_special_judge": False,
    }


def _arch_fence(body: dict[str, Any]) -> str:
    return f"```json\n{json.dumps(body)}\n```"


# =============================================================================
# _parse_and_validate — 5 failure 분기 + 1 success
# (M3 dual-call rollback 후에도 single call 검증으로 동일 사용)
# =============================================================================


class TestParseAndValidate:
    def test_valid_response_parsed(self) -> None:
        body = _arch_body()
        data, err = _parse_and_validate(_arch_fence(body))
        assert err is None
        assert data is not None
        assert data["problem_title"] == "A+B"

    def test_unparseable_json_returns_error(self) -> None:
        data, err = _parse_and_validate("not a JSON at all")
        assert data is None
        assert err is not None
        assert "JSON parse error" in err

    def test_non_dict_returns_error(self) -> None:
        data, err = _parse_and_validate("```json\n[1, 2, 3]\n```")
        assert data is None
        assert err == "output is not a JSON object"

    def test_missing_field_returns_error(self) -> None:
        body = _arch_body()
        del body["problem_description"]
        data, err = _parse_and_validate(_arch_fence(body))
        assert data is None
        assert err is not None
        assert "missing fields" in err
        assert "problem_description" in err

    def test_too_few_samples_returns_error(self) -> None:
        body = _arch_body(n_samples=2)
        data, err = _parse_and_validate(_arch_fence(body))
        assert data is None
        assert err is not None
        assert "too few sample_testcases" in err

    def test_invalid_constraints_returns_error(self) -> None:
        body = _arch_body()
        del body["constraints_structured"]["time_limit_ms"]
        data, err = _parse_and_validate(_arch_fence(body))
        assert data is None
        assert err is not None
        assert "constraints_structured invalid" in err


# =============================================================================
# run — single Opus call (M3 rollback 후)
# =============================================================================


class TestRunArchitect:
    def _stub_chat(self, monkeypatch: pytest.MonkeyPatch, content: str) -> None:
        chat = _make_chat(content)
        monkeypatch.setattr("ipe.nodes.architect.get_chat", lambda *a, **k: chat)

    def _initial_state(self) -> ProblemState:
        return {"target_algorithm": "A+B", "target_language": "python"}

    def test_valid_response_populates_state(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        body = _arch_body(title="Valid Problem")
        self._stub_chat(monkeypatch, _arch_fence(body))

        out = run(self._initial_state(), tracker=_make_tracker(tmp_path))

        assert out.get("last_failed_node") is None
        assert out.get("problem_title") == "Valid Problem"
        assert out.get("feedback_message") is None
        # M3 rollback: architect_candidates / architect_consensus 가 채워지지 않아야
        assert "architect_candidates" not in out or out.get("architect_candidates") in (None, [])
        assert "architect_consensus" not in out or not out.get("architect_consensus")

    def test_parse_failure_routes_back(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._stub_chat(monkeypatch, "garbage non-json")

        out = run(self._initial_state(), tracker=_make_tracker(tmp_path))

        assert out["last_failed_node"] == "architect"
        fb = out.get("feedback_message") or ""
        assert "Architect failed validation" in fb

    def test_records_single_llm_call(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """M3 rollback 후 architect 는 항상 1 LLM call 만 기록 (dual 아님)."""
        body = _arch_body()
        self._stub_chat(monkeypatch, _arch_fence(body))

        out = run(self._initial_state(), tracker=_make_tracker(tmp_path))

        calls = out.get("llm_calls") or []
        assert len(calls) == 1
        assert calls[0].get("node") == "architect"
        assert calls[0].get("model") == "claude-opus-4-7"
