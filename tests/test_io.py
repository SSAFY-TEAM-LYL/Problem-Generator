"""io.py 단위 테스트 (P10.4).

스펙: PROJECT_SPEC.md §6, IMPLEMENTATION_ROADMAP §1 P10.4
범위: ``_slug`` (한글/특수문자) + 내부 빌더들 (_summarize_llm_calls /
_build_difficulty / _render_problem_md).

full cycle은 ``tests/integration/test_save_result.py`` 에서 검증.
"""

from __future__ import annotations

from typing import Any

from ipe._io_render import render_problem_md
from ipe.io import (
    _build_difficulty,
    _build_testcase_manifest,
    _slug,
    _summarize_llm_calls,
)
from ipe.state import ProblemState

# =============================================================================
# _slug — 한글/특수문자/공백
# =============================================================================


class TestSlug:
    def test_empty_returns_unnamed(self) -> None:
        assert _slug("") == "unnamed"
        assert _slug("   ") == "unnamed"

    def test_alphanumeric_preserved(self) -> None:
        assert _slug("Two_Sum-123") == "Two_Sum-123"

    def test_korean_replaced_with_underscore(self) -> None:
        # 한글 4자 → 하나의 underscore 시퀀스, dedup + strip 후 빈 → "unnamed"
        assert _slug("최단경로") == "unnamed"

    def test_korean_with_alphanum_kept(self) -> None:
        out = _slug("다익스트라 algorithm")
        assert "algorithm" in out
        # 한글은 underscore로 치환됨
        assert "다" not in out

    def test_spaces_become_underscore(self) -> None:
        assert _slug("hello world") == "hello_world"

    def test_special_chars_become_underscore(self) -> None:
        assert _slug("a/b<>c?") == "a_b_c"

    def test_consecutive_underscores_compressed(self) -> None:
        assert _slug("a___b") == "a_b"
        assert _slug("a   b") == "a_b"

    def test_max_len_truncation(self) -> None:
        long = "a" * 100
        assert len(_slug(long, max_len=10)) == 10

    def test_only_special_chars_returns_unnamed(self) -> None:
        assert _slug("///") == "unnamed"
        assert _slug("___") == "unnamed"  # strip 후 빈


# =============================================================================
# _summarize_llm_calls
# =============================================================================


class TestSummarizeLLMCalls:
    def test_empty_calls(self) -> None:
        out = _summarize_llm_calls([])
        assert out["total_calls"] == 0
        assert out["total_input_tokens"] == 0
        assert out["total_cost_usd"] == 0.0
        assert out["by_node"] == {}

    def test_aggregates_tokens_and_cost(self) -> None:
        calls = [
            {"node": "architect", "input_tokens": 100, "output_tokens": 50,
             "cost_usd": 0.005, "seq": 0, "model": "x", "timestamp": ""},
            {"node": "coder", "input_tokens": 200, "output_tokens": 80,
             "cost_usd": 0.01, "seq": 1, "model": "x", "timestamp": ""},
            {"node": "coder", "input_tokens": 150, "output_tokens": 60,
             "cost_usd": 0.008, "seq": 2, "model": "x", "timestamp": ""},
        ]
        out = _summarize_llm_calls(calls)  # type: ignore[arg-type]
        assert out["total_calls"] == 3
        assert out["total_input_tokens"] == 450
        assert out["total_output_tokens"] == 190
        assert out["total_cost_usd"] == 0.023
        assert out["by_node"] == {"architect": 1, "coder": 2}


# =============================================================================
# _build_difficulty
# =============================================================================


class TestBuildDifficulty:
    def test_none_label_returns_none(self) -> None:
        state: ProblemState = {}
        assert _build_difficulty(state) is None

    def test_full_difficulty(self) -> None:
        state: ProblemState = {
            "difficulty_label": "Bronze V",
            "difficulty_reasoning": "Closest to bj_1000_bronze5",
            "difficulty_factors": {"algorithm": "implementation"},
            "difficulty_calibration_anchors": [
                {"id": "bj_1000_bronze5", "label": "Bronze V"},
                {"id": "bj_2557_bronze5", "label": "Bronze V"},
            ],
        }
        out = _build_difficulty(state)
        assert out is not None
        assert out["label"] == "Bronze V"
        assert out["reasoning"] == "Closest to bj_1000_bronze5"
        assert out["factors"] == {"algorithm": "implementation"}
        assert out["calibration_anchors"] == ["bj_1000_bronze5", "bj_2557_bronze5"]

    def test_missing_factors_defaults_to_empty_dict(self) -> None:
        state: ProblemState = {"difficulty_label": "Gold V"}
        out = _build_difficulty(state)
        assert out is not None
        assert out["factors"] == {}
        assert out["calibration_anchors"] == []


# =============================================================================
# _build_testcase_manifest
# =============================================================================


def test_testcase_manifest_indexing() -> None:
    """1-indexed + zero-padded filename."""
    cases = [
        {"kind": "sample", "input": "1\n", "expected_output": "1"},
        {"kind": "adversarial", "category": "MIN", "execution_time_ms": 12},
        {"kind": "generated", "generator": "gen_small", "seed": 3,
         "execution_time_ms": 45},
    ]
    out = _build_testcase_manifest(cases)
    assert len(out) == 3
    assert out[0]["index"] == 1
    assert out[0]["filename"] == "01"
    assert out[1]["index"] == 2
    assert out[1]["filename"] == "02"
    assert out[2]["generator"] == "gen_small"
    assert out[2]["seed"] == 3
    assert out[2]["exec_time_ms"] == 45


# =============================================================================
# _render_problem_md
# =============================================================================


def test_render_problem_md_minimal() -> None:
    """제목 + 설명 + 솔루션이 있는 minimal state → markdown 핵심 sections 포함."""
    state: ProblemState = {
        "problem_title": "Two Sum",
        "problem_description": "Given two integers, print sum.",
        "constraints": "1 <= a, b <= 10^9",
        "target_language": "python",
        "solution_code": "a, b = map(int, input().split())\nprint(a + b)",
        "sample_testcases": [
            {"input": "1 2\n", "expected_output": "3"},
        ],
    }
    md = render_problem_md(state, manifest=[], difficulty=_build_difficulty(state))
    assert md.startswith("# Two Sum")
    assert "## Description" in md
    assert "Given two integers" in md
    assert "## Constraints" in md
    assert "## Sample Testcases" in md
    assert "### Sample 1" in md
    assert "## Golden Solution" in md
    assert "```python" in md


def test_render_problem_md_with_difficulty() -> None:
    """difficulty 블록 포함 — label/reasoning/calibration_anchors 모두 출력."""
    state: ProblemState = {
        "target_algorithm": "A+B",
        "difficulty_label": "Bronze V",
        "difficulty_reasoning": "Closest to bj_1000_bronze5",
        "difficulty_factors": {"algorithm": "implementation"},
        "difficulty_calibration_anchors": [
            {"id": "bj_1000_bronze5", "label": "Bronze V"},
        ],
    }
    md = render_problem_md(state, manifest=[], difficulty=_build_difficulty(state))
    assert "## Difficulty" in md
    assert "Bronze V" in md
    assert "bj_1000_bronze5" in md


def test_render_problem_md_manifest_table() -> None:
    """manifest가 있으면 GFM 테이블 출력."""
    state: ProblemState = {"problem_title": "X"}
    manifest: list[dict[str, Any]] = [
        {"index": 1, "kind": "sample", "category": None, "generator": None,
         "seed": None, "exec_time_ms": 10},
        {"index": 2, "kind": "generated", "category": "MAX_STRESS",
         "generator": "gen_big", "seed": 7, "exec_time_ms": 250},
    ]
    md = render_problem_md(state, manifest=manifest, difficulty=None)
    assert "## Testcase Manifest" in md
    assert "| # | kind |" in md
    assert "gen_big" in md
    assert "MAX_STRESS" in md
