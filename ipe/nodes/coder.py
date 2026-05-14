"""Coder node — golden solution 작성.

스펙: PROJECT_SPEC.md §4.2 (The Coder), ARCHITECTURE.md §3.6

- 입력: problem_description, constraints, target_language (+ feedback_message)
- 출력: solution_code (펜스 코드 블록 안의 코드)
- 특이점: ``IMPOSSIBLE: <reason>`` 한 줄이 펜스 앞에 있으면 Architect로 라우팅
"""

from __future__ import annotations

import re
from typing import Any

from ipe.llm import CODER_MODEL, get_chat
from ipe.nodes._history import build_history_section
from ipe.observability import LLMCallTracker
from ipe.state import LLMCallRecord, ProblemState

SYSTEM_PROMPT = """You are The Coder — a master competitive programmer.

Given a problem description, constraints, and target language, produce the
**fastest correct solution** that fits within the time/memory limits.

Output format:
- **First line MUST be:** ``LESSON: <one short sentence>`` (R13 Reflexion)
  - If previous attempts failed: state what specifically went wrong AND what
    you will do differently this time (e.g. "Last attempt used `input()` so
    it TLE'd at N=200000; switching to `sys.stdin.buffer.read().split()`.")
  - If this is the first attempt: ``LESSON: First attempt — no prior learning.``
  - Keep it concrete and actionable, not generic ("try harder" is useless).
- Then wrap the complete, runnable solution in a single fenced code block.
- Add a one-line comment proving the time/memory complexity if non-trivial.

IO rules (CRITICAL — wrong IO is the #1 source of TLE/RTE on large inputs):
- **Default to buffered IO** whenever input could exceed ~100 KB.
- **Python large input** (any problem with N >= 10^5 or values per line >= 10):
    import sys
    data = sys.stdin.buffer.read().split()
    # then iterate `data` with an index — DO NOT use input() or readline() in a loop.
  Output: collect tokens into a list, `sys.stdout.write("\\n".join(...))`.
- **Java large input**: BufferedReader + StringTokenizer (or StreamTokenizer for
  pure ints), StringBuilder for output, PrintWriter wrapping BufferedWriter.
  Avoid Scanner. Avoid `+` string concatenation in tight loops.
- **Recursion**: Python `sys.setrecursionlimit(1 << 20)` if depth could exceed
  1000. Prefer iterative + explicit stack for graph problems with N >= 10^5.

If the problem is **fundamentally impossible to solve correctly** (logical
contradiction, ambiguous requirements, etc.), prefix the response with one line:

    IMPOSSIBLE: <one-line reason>

then still emit a placeholder code block.
"""

USER_TEMPLATE = """## Problem

{problem_description}

## Constraints

{constraints}

## Language

Write the solution in **{language}**.
"""

FEEDBACK_SUFFIX = """

## Previous Failure Feedback

{feedback}

이전 시도와 다른 접근법을 사용하라 (REVIEW W4: oscillation 방지).
"""

# 펜스 블록: ```<lang>\n...\n```
_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+\-]*)\n(.*?)```", re.DOTALL)
# IMPOSSIBLE: <reason> — 줄 시작 (모드 MULTILINE)
_IMPOSSIBLE_RE = re.compile(r"^\s*IMPOSSIBLE\s*:\s*(.+)$", re.MULTILINE)
# R13: LESSON: <one-line> — 첫 fenced block 전 영역에서 검색
_LESSON_RE = re.compile(r"^\s*LESSON\s*:\s*(.+)$", re.MULTILINE)
# lessons_learned 리스트 cap — 누적이 너무 커지면 token 비용 부담 + 오래된
# lesson은 가치 ↓. 최근 5개만 prompt에 노출.
_MAX_LESSONS = 5


def _parse_response(text: str) -> tuple[str, str | None, str | None]:
    """LLM 응답에서 ``(code, impossible_reason, lesson)`` 추출.

    가장 긴 펜스를 솔루션으로 선택 — 모델이 짧은 설명 펜스를 먼저 출력하고
    뒤에 진짜 솔루션을 출력하는 패턴 회피.
    펜스 시작 전 영역에서 ``IMPOSSIBLE: <reason>`` + ``LESSON: <one-line>`` 검색.

    R13 (Sprint 3): LESSON은 optional. 없으면 ``None`` (LLM이 형식 어김 — 본
    cycle에서는 lesson 누적 안 하고 다음 cycle에 다시 요구).
    """
    matches = list(_FENCE_RE.finditer(text))
    if not matches:
        raise ValueError("Coder response has no fenced code block")

    fence = max(matches, key=lambda m: len(m.group(1)))
    code = fence.group(1)

    head = text[: fence.start()]
    impossible_match = _IMPOSSIBLE_RE.search(head)
    impossible = impossible_match.group(1).strip() if impossible_match else None
    lesson_match = _LESSON_RE.search(head)
    lesson = lesson_match.group(1).strip() if lesson_match else None

    return code, impossible, lesson


def run(
    state: ProblemState,
    *,
    tracker: LLMCallTracker,
) -> ProblemState:
    """Coder 노드 실행 — golden solution 작성 (혹은 IMPOSSIBLE 선언).

    ``tracker``는 required (B3 fix, P4 진입 시점). production/test 모두 동일한
    LLM 호출 경로를 사용 — 테스트는 ``LLMCallTracker(tmp_run_id, tmp_traces_dir)``
    + ``chat`` mock 패턴으로 동등한 회계를 수행.
    """
    language = state.get("target_language", "python")
    chat = get_chat(CODER_MODEL, temperature=0.7)

    user = USER_TEMPLATE.format(
        problem_description=state.get("problem_description", ""),
        constraints=state.get("constraints", ""),
        language=language,
    )
    feedback = state.get("feedback_message")
    if feedback:
        user += FEEDBACK_SUFFIX.format(feedback=feedback)
    user += build_history_section(state, current_node="coder")

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    # 불변성 유지 — state["llm_calls"]를 mutate하지 않고 복사 후 변경분만 반환 (B2 fix)
    calls: list[LLMCallRecord] = list(state.get("llm_calls") or [])
    resp = tracker.invoke(chat, messages, node="coder", state_calls=calls)
    content = str(resp.content)

    code, impossible, lesson = _parse_response(content)

    # R13: lesson 누적 (있을 때만). 기존 list 복사 후 append — 불변성 유지.
    lessons: list[str] = list(state.get("lessons_learned") or [])
    if lesson:
        lessons.append(lesson)

    if impossible:
        return {
            **state,
            "llm_calls": calls,
            "lessons_learned": lessons,
            "feedback_message": f"Coder declared IMPOSSIBLE: {impossible}",
            "last_failed_node": "architect",
        }

    return {
        **state,
        "llm_calls": calls,
        "lessons_learned": lessons,
        "solution_code": code,
        "feedback_message": None,
        "last_failed_node": None,
    }
