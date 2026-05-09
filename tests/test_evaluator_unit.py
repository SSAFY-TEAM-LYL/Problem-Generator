"""evaluator.py 단위 테스트 (polish round D2).

스펙: ARCHITECTURE.md §3.10, IMPLEMENTATION_ROADMAP §1 P9.2
범위: ``_build_anchor_block`` / ``_testcases_excerpt`` private helpers.
``run()`` 자체는 ``tests/integration/test_evaluator.py`` 가 cover.
"""

from __future__ import annotations

from typing import Any

from ipe.nodes.evaluator import _build_anchor_block, _testcases_excerpt


class TestBuildAnchorBlock:
    def test_empty_anchors(self) -> None:
        out = _build_anchor_block([])
        assert "(no anchors loaded)" in out
        assert "Calibration Anchors" in out

    def test_single_anchor_renders(self) -> None:
        anchors = [
            {
                "id": "bj_1000_bronze5",
                "label": "Bronze V",
                "summary": "A+B",
                "factors": {"algorithm": "implementation", "n_max": 1},
            }
        ]
        out = _build_anchor_block(anchors)
        assert "### bj_1000_bronze5 — Bronze V" in out
        assert "summary: A+B" in out
        assert '"algorithm"' in out  # factors JSON에 포함
        assert '"implementation"' in out

    def test_multiple_anchors(self) -> None:
        anchors = [
            {"id": "a1", "label": "L1", "summary": "s1", "factors": {}},
            {"id": "a2", "label": "L2", "summary": "s2", "factors": {}},
        ]
        out = _build_anchor_block(anchors)
        assert "### a1 — L1" in out
        assert "### a2 — L2" in out

    def test_factors_korean_preserves_unicode(self) -> None:
        """ensure_ascii=False 로 한글 보존."""
        anchors = [
            {"id": "x", "label": "L", "summary": "한글", "factors": {"비고": "한글값"}}
        ]
        out = _build_anchor_block(anchors)
        assert "한글" in out
        assert "비고" in out

    def test_missing_factors_defaults_to_empty_dict(self) -> None:
        """factors 키 없거나 None → 빈 dict로 처리."""
        anchors = [{"id": "x", "label": "L", "summary": "s"}]  # factors 없음
        out = _build_anchor_block(anchors)
        # factors: {} 라인 (JSON empty dict)
        assert "factors: {}" in out

    def test_missing_id_label_falls_back_to_question(self) -> None:
        """id/label 없으면 '?' fallback."""
        anchors: list[dict[str, Any]] = [{"summary": "s", "factors": {}}]
        out = _build_anchor_block(anchors)
        assert "### ? — ?" in out


class TestTestcasesExcerpt:
    def test_empty_testcases(self) -> None:
        assert _testcases_excerpt([]) == "(no testcases)"

    def test_renders_first_three(self) -> None:
        cases = [
            {"input": "1", "expected_output": "1", "kind": "sample"},
            {"input": "2", "expected_output": "4", "kind": "adversarial"},
            {"input": "3", "expected_output": "9", "kind": "generated"},
            {"input": "4", "expected_output": "16", "kind": "generated"},  # 표시 안 됨
        ]
        out = _testcases_excerpt(cases)
        assert "[sample]" in out
        assert "[adversarial]" in out
        assert "[generated]" in out
        # 4번째 case는 truncate (MAX_TESTCASE_EXCERPT=3)
        assert out.count("\n") == 2  # 3 lines = 2 newlines

    def test_missing_kind_shows_question(self) -> None:
        cases = [{"input": "x", "expected_output": "y"}]
        out = _testcases_excerpt(cases)
        assert "[?]" in out

    def test_long_input_truncated(self) -> None:
        """TESTCASE_FIELD_MAX_CHARS=80 — 긴 input/expected는 절단."""
        long_input = "x" * 200
        cases = [{"input": long_input, "expected_output": "ok"}]
        out = _testcases_excerpt(cases)
        # 80자로 truncated → 200자 그대로 X
        assert "x" * 200 not in out
        assert "x" * 80 in out

    def test_multiline_input_collapsed(self) -> None:
        """\\n은 공백으로 치환 (한 줄 표시)."""
        cases = [{"input": "line1\nline2\n", "expected_output": "ok"}]
        out = _testcases_excerpt(cases)
        # entry는 한 줄 — input의 \n은 공백으로
        first_entry = out.split("\n")[0]
        # input 부분에 raw \n 없어야
        assert "line1\nline2" not in first_entry
        assert "line1 line2" in first_entry
