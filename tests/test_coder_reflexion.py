"""Unit tests — Coder R13 Reflexion (lesson 추출 + 누적).

배경: v0.2.0 Sprint 3 R13 — Coder가 매 응답 시작 시 ``LESSON: <one-line>``을
출력하여 history에 누적. 본 테스트는 ``_parse_response``의 lesson 추출 +
``build_history_section``의 lessons 노출을 deterministic하게 검증.

LLM 없이 순수 텍스트 파싱 + state dict 입력으로 검증 — fast/cheap.
"""

from __future__ import annotations

from ipe.nodes._history import _MAX_LESSONS_IN_PROMPT, build_history_section
from ipe.nodes.coder import _parse_response
from ipe.state import ProblemState


class TestParseResponseLesson:
    """``_parse_response``가 LESSON: 라인을 추출하는지."""

    def test_lesson_extracted_when_present(self) -> None:
        text = (
            "LESSON: Last attempt used input() so it TLE'd; "
            "switching to sys.stdin.buffer.read().split().\n"
            "\n"
            "```python\n"
            "import sys\n"
            "data = sys.stdin.buffer.read().split()\n"
            "```\n"
        )
        code, _brute, impossible, lesson = _parse_response(text)
        assert "sys.stdin.buffer.read" in code
        assert impossible is None
        assert lesson is not None
        assert "TLE" in lesson
        assert "sys.stdin.buffer.read" in lesson

    def test_lesson_none_when_missing(self) -> None:
        text = "```python\nprint('hello')\n```\n"
        code, _brute, impossible, lesson = _parse_response(text)
        assert code.strip() == "print('hello')"
        assert impossible is None
        assert lesson is None

    def test_lesson_extracted_with_impossible(self) -> None:
        text = (
            "LESSON: First attempt — no prior learning.\n"
            "IMPOSSIBLE: contradictory constraints\n"
            "```python\n"
            "pass\n"
            "```\n"
        )
        code, _brute, impossible, lesson = _parse_response(text)
        assert impossible == "contradictory constraints"
        assert lesson == "First attempt — no prior learning."

    def test_lesson_only_first_match_when_multiple(self) -> None:
        """첫 LESSON 줄만 채택 — 솔루션 코드 안의 LESSON: 주석은 무시."""
        text = (
            "LESSON: Use heapq for Dijkstra.\n"
            "```python\n"
            "# LESSON: this comment should NOT be parsed as the lesson\n"
            "from heapq import heappush\n"
            "```\n"
        )
        _, _, _, lesson = _parse_response(text)
        assert lesson == "Use heapq for Dijkstra."

    def test_lesson_with_extra_whitespace(self) -> None:
        text = "  LESSON:   Trim spaces correctly.   \n```python\npass\n```"
        _, _, _, lesson = _parse_response(text)
        assert lesson == "Trim spaces correctly."

    def test_lesson_inside_code_block_not_extracted(self) -> None:
        """펜스 안의 LESSON: 주석은 head 영역 밖이므로 무시 — head 빈 경우."""
        text = "```python\n# LESSON: comment\nprint(1)\n```"
        _, _, _, lesson = _parse_response(text)
        assert lesson is None  # head는 빈 문자열


class TestBuildHistoryLessons:
    """``build_history_section``이 coder 호출 시 lessons를 노출하는지."""

    def _state_with_lessons(self, lessons: list[str]) -> ProblemState:
        return {
            "iteration_history": [
                {
                    "iter_index": 1, "node": "coder",
                    "error_signature": "abc", "feedback": "fail msg",
                },
            ],
            "lessons_learned": lessons,
        }

    def test_lessons_shown_for_coder(self) -> None:
        state = self._state_with_lessons(["Use buffered IO.", "Try heapq."])
        out = build_history_section(state, current_node="coder")
        assert "## Learned Lessons" in out
        assert "Use buffered IO." in out
        assert "Try heapq." in out

    def test_lessons_hidden_for_non_coder(self) -> None:
        state = self._state_with_lessons(["Use buffered IO."])
        for node in ("architect", "auditor", "generator", "evaluator"):
            out = build_history_section(state, current_node=node)
            assert "Learned Lessons" not in out
            assert "Use buffered IO." not in out

    def test_lessons_section_skipped_when_empty(self) -> None:
        state = self._state_with_lessons([])
        out = build_history_section(state, current_node="coder")
        assert "Learned Lessons" not in out

    def test_lessons_cap_at_max(self) -> None:
        """최근 _MAX_LESSONS_IN_PROMPT(5)개만 노출."""
        lessons = [f"Lesson {i}" for i in range(10)]
        state = self._state_with_lessons(lessons)
        out = build_history_section(state, current_node="coder")
        # 오래된 lesson 0~4는 prune, 최근 5~9만 노출
        assert "Lesson 0" not in out
        assert "Lesson 4" not in out
        assert "Lesson 5" in out
        assert "Lesson 9" in out
        assert _MAX_LESSONS_IN_PROMPT == 5

    def test_lessons_not_shown_without_history(self) -> None:
        """iteration_history 없으면 build_history_section 자체가 빈 문자열 반환."""
        state: ProblemState = {"lessons_learned": ["Use buffered IO."]}
        out = build_history_section(state, current_node="coder")
        assert out == ""


class TestParseResponseBrute:
    """R15: ``_parse_response``가 두 번째 펜스를 brute로 추출."""

    def test_brute_extracted_when_two_fences(self) -> None:
        text = (
            "LESSON: First attempt.\n"
            "GOLDEN:\n"
            "```python\n"
            "import sys\n"
            "from collections import defaultdict\n"
            "data = sys.stdin.buffer.read().split()\n"
            "# fast hash-based golden solution with many lines for length\n"
            "```\n"
            "\n"
            "BRUTE:\n"
            "```python\n"
            "n = int(input())\n"
            "```\n"
        )
        code, brute, _, _ = _parse_response(text)
        # golden = 가장 긴 펜스
        assert "sys.stdin.buffer.read" in code
        assert "defaultdict" in code
        # brute = 두 번째 펜스 (더 짧음)
        assert brute is not None
        assert brute.strip() == "n = int(input())"

    def test_brute_none_when_single_fence(self) -> None:
        text = "```python\nprint(1)\n```"
        _, brute, _, _ = _parse_response(text)
        assert brute is None

    def test_brute_none_for_legacy_response(self) -> None:
        """기존 R13 응답 (단일 fence)은 brute=None 안전 처리."""
        text = (
            "LESSON: legacy single-fence response.\n"
            "```python\n"
            "solution = 1\n"
            "```\n"
        )
        code, brute, _, lesson = _parse_response(text)
        assert code.strip() == "solution = 1"
        assert brute is None
        assert lesson == "legacy single-fence response."
