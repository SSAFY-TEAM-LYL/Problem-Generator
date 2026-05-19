"""architect.py M3 multi-model consensus 단위 테스트 (v0.3.0 RFC §M3).

스펙: docs/rfc/v0.3.0_multi-mechanism.md §M3
범위: Opus + Sonnet 순차 호출 + structural diff voting + 4 경로 (match / opus_only /
sonnet_only / retry).

기존 ``test_architect_unit.py``는 single-model 시절의 validator/route_back만 cover —
본 파일이 M3 specific consensus 로직 보강.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.nodes.architect import (
    _parse_and_validate,
    _structural_match,
    _summarize,
    run,
)
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
# _structural_match — consensus 판정 핵심
# =============================================================================


class TestStructuralMatch:
    def test_identical_structure_matches(self) -> None:
        a = _arch_body()
        b = _arch_body()
        assert _structural_match(a, b) is True

    def test_different_titles_still_match(self) -> None:
        """제목/설명은 비교 X — 자연어 표현은 모델마다 달라도 정상."""
        a = _arch_body(title="A+B")
        b = _arch_body(title="Sum of Two")
        assert _structural_match(a, b) is True

    def test_different_time_limit_does_not_match(self) -> None:
        a = _arch_body(time_ms=2000)
        b = _arch_body(time_ms=3000)
        assert _structural_match(a, b) is False

    def test_different_memory_limit_does_not_match(self) -> None:
        a = _arch_body(mem_mb=256)
        b = _arch_body(mem_mb=512)
        assert _structural_match(a, b) is False

    def test_different_variable_count_does_not_match(self) -> None:
        a = _arch_body(var_names=("a", "b"))
        b = _arch_body(var_names=("a", "b", "c"))
        assert _structural_match(a, b) is False

    def test_different_variable_names_does_not_match(self) -> None:
        """이름이 다르면 같은 개수라도 fail — semantic mismatch."""
        a = _arch_body(var_names=("x", "y"))
        b = _arch_body(var_names=("p", "q"))
        assert _structural_match(a, b) is False

    def test_same_variable_names_in_different_order_matches(self) -> None:
        """정렬 후 비교 — 순서만 다른 건 match."""
        a = _arch_body(var_names=("a", "b"))
        b = _arch_body(var_names=("b", "a"))
        assert _structural_match(a, b) is True

    def test_different_sample_count_does_not_match(self) -> None:
        a = _arch_body(n_samples=3)
        b = _arch_body(n_samples=5)
        assert _structural_match(a, b) is False

    def test_missing_constraints_structured_does_not_match(self) -> None:
        a: dict[str, Any] = {"sample_testcases": []}
        b = _arch_body()
        assert _structural_match(a, b) is False


# =============================================================================
# _summarize — feedback line 빌더
# =============================================================================


class TestSummarize:
    def test_includes_key_structural_fields(self) -> None:
        body = _arch_body(time_ms=2000, mem_mb=256, var_names=("a", "b"), n_samples=3)
        out = _summarize(body)
        assert "tl=2000ms" in out
        assert "ml=256MB" in out
        assert "vars=2" in out
        assert "samples=3" in out

    def test_handles_missing_constraints_structured(self) -> None:
        out = _summarize({"sample_testcases": [1, 2]})
        # 빈 cs면 None이지만 string화는 깨지지 않아야
        assert "samples=2" in out


# =============================================================================
# run — 5 경로 voting 결정 (match / opus_only / sonnet_only / both_invalid / diff)
# =============================================================================


class TestRunConsensus:
    def _stub_dual_call(
        self,
        monkeypatch: pytest.MonkeyPatch,
        opus_content: str,
        sonnet_content: str,
    ) -> None:
        """``get_chat``이 호출 순서대로 (Opus, Sonnet) chat을 반환하도록 stub.

        architect.run은 ``get_chat(ARCHITECT_MODEL)`` → ``get_chat(CONSENSUS_MODEL)``
        순. 그러므로 sequence list로 pop.
        """
        chats = [
            _make_chat(opus_content, "claude-opus-4-7"),
            _make_chat(sonnet_content, "claude-sonnet-4-6"),
        ]

        def fake_get_chat(model: str, *a: Any, **k: Any) -> MagicMock:
            return chats.pop(0)

        monkeypatch.setattr("ipe.nodes.architect.get_chat", fake_get_chat)

    def _initial_state(self) -> ProblemState:
        return {"target_algorithm": "A+B", "target_language": "python"}

    def test_match_consensus_adopts_opus(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """둘 다 valid + structural match → consensus='match', Opus 채택."""
        opus_body = _arch_body(title="Opus Title")
        sonnet_body = _arch_body(title="Sonnet Title")  # 제목만 다름
        self._stub_dual_call(
            monkeypatch, _arch_fence(opus_body), _arch_fence(sonnet_body)
        )

        out = run(self._initial_state(), tracker=_make_tracker(tmp_path))

        assert out.get("last_failed_node") is None
        assert out.get("architect_consensus") == "match"
        assert out.get("problem_title") == "Opus Title"  # Opus 채택
        assert len(out.get("architect_candidates") or []) == 2

    def test_opus_only_graceful_when_sonnet_invalid(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Opus valid + Sonnet 망가짐 → Opus 채택, consensus='opus_only'."""
        self._stub_dual_call(
            monkeypatch,
            _arch_fence(_arch_body(title="Opus Solo")),
            "not valid json from sonnet",
        )

        out = run(self._initial_state(), tracker=_make_tracker(tmp_path))

        assert out.get("last_failed_node") is None
        assert out.get("architect_consensus") == "opus_only"
        assert out.get("problem_title") == "Opus Solo"
        assert len(out.get("architect_candidates") or []) == 1

    def test_sonnet_only_graceful_when_opus_invalid(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Opus 망가짐 + Sonnet valid → Sonnet 채택, consensus='sonnet_only'."""
        self._stub_dual_call(
            monkeypatch,
            "garbage from opus",
            _arch_fence(_arch_body(title="Sonnet Solo")),
        )

        out = run(self._initial_state(), tracker=_make_tracker(tmp_path))

        assert out.get("last_failed_node") is None
        assert out.get("architect_consensus") == "sonnet_only"
        assert out.get("problem_title") == "Sonnet Solo"
        assert len(out.get("architect_candidates") or []) == 1

    def test_both_invalid_routes_back(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """둘 다 invalid → architect retry."""
        self._stub_dual_call(monkeypatch, "garbage 1", "garbage 2")

        out = run(self._initial_state(), tracker=_make_tracker(tmp_path))

        assert out["last_failed_node"] == "architect"
        fb = out.get("feedback_message") or ""
        assert "both Opus and Sonnet architects failed validation" in fb
        # 둘 다 parse 실패 시 candidates 비어 있어야
        assert (out.get("architect_candidates") or []) == []

    def test_structural_diff_routes_back(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """둘 다 valid인데 time_limit_ms 다름 → consensus 실패 → retry."""
        self._stub_dual_call(
            monkeypatch,
            _arch_fence(_arch_body(time_ms=2000)),
            _arch_fence(_arch_body(time_ms=5000)),
        )

        out = run(self._initial_state(), tracker=_make_tracker(tmp_path))

        assert out["last_failed_node"] == "architect"
        fb = out.get("feedback_message") or ""
        assert "disagree on structure" in fb
        # 둘 다 valid면 candidates에 모두 저장 (분석용)
        assert len(out.get("architect_candidates") or []) == 2

    def test_records_two_llm_calls(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """M3는 항상 2 LLM call 기록 — Opus + Sonnet 순차."""
        body = _arch_body()
        self._stub_dual_call(monkeypatch, _arch_fence(body), _arch_fence(body))

        out = run(self._initial_state(), tracker=_make_tracker(tmp_path))

        calls = out.get("llm_calls") or []
        assert len(calls) == 2
        # 두 호출 모두 architect 노드
        assert all(c.get("node") == "architect" for c in calls)
        # 두 모델 모두 호출됨
        models = {c.get("model") for c in calls}
        assert "claude-opus-4-7" in models
        assert "claude-sonnet-4-6" in models
