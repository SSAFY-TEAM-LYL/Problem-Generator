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

Output format (R15 Brute Cross-check — produce TWO solutions):
- **First line MUST be:** ``LESSON: <one short sentence>`` (R13 Reflexion)
  - If previous attempts failed: state what specifically went wrong AND what
    you will do differently this time (e.g. "Last attempt used `input()` so
    it TLE'd at N=200000; switching to `sys.stdin.buffer.read().split()`.")
  - If this is the first attempt: ``LESSON: First attempt — no prior learning.``
  - Keep it concrete and actionable, not generic ("try harder" is useless).

- **GOLDEN solution** (first fenced code block, longest) — fast, correct,
  fits within constraints. Add one-line complexity comment if non-trivial.

- **BRUTE solution** (second fenced code block) — naive, definitely-correct
  reference implementation for small N (≤ 30). Used for cross-check, NEVER
  for actual submission. Examples:
  - Two Sum (golden: hash O(N)) → brute: O(N²) double loop
  - Dijkstra (golden: heap O((V+E)logV)) → brute: O(V²) array-scan
  - LIS (golden: binary search O(N logN)) → brute: O(N²) DP
  - Segment Tree (golden: O(logN) per op) → brute: O(N) per op linear scan
  The brute solution MUST:
  - Read same input format, write same output format
  - Be obviously correct (simple, no optimizations)
  - Handle small N only (will TLE on large N — that's expected)
  - Be a complete runnable program in the target language

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


def _parse_response(
    text: str,
) -> tuple[str, str | None, str | None, str | None]:
    """LLM 응답에서 ``(code, brute, impossible_reason, lesson)`` 추출.

    가장 긴 펜스 = golden solution. 두 번째 펜스 (있을 때) = brute solution
    (R15 cross-check 용). 펜스 1개만 있으면 brute=None — LLM 형식 어김 또는
    이전 phase 출력. brute 부재 시 cross-check 생략 (안전 fallback).

    펜스 시작 전 영역에서 ``IMPOSSIBLE: <reason>`` + ``LESSON: <one-line>`` 검색.

    R13: LESSON은 optional (없으면 None — 다음 cycle 재요구).
    R15: brute는 optional (없으면 None — cross-check skip).
    """
    matches = list(_FENCE_RE.finditer(text))
    if not matches:
        raise ValueError("Coder response has no fenced code block")

    # golden = 가장 긴 펜스 (LLM이 설명 펜스 먼저 출력하는 패턴 회피)
    fence_sorted = sorted(matches, key=lambda m: -len(m.group(1)))
    golden_fence = fence_sorted[0]
    code = golden_fence.group(1)

    # brute = 두 번째 펜스 (있을 때만). golden 펜스 자체는 제외.
    brute: str | None = None
    if len(fence_sorted) >= 2:
        brute = fence_sorted[1].group(1)

    # IMPOSSIBLE / LESSON은 가장 앞 펜스 시작 전 영역에서 검색
    earliest_fence = min(matches, key=lambda m: m.start())
    head = text[: earliest_fence.start()]
    impossible_match = _IMPOSSIBLE_RE.search(head)
    impossible = impossible_match.group(1).strip() if impossible_match else None
    lesson_match = _LESSON_RE.search(head)
    lesson = lesson_match.group(1).strip() if lesson_match else None

    return code, brute, impossible, lesson


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

    # M1 (v0.3.0 RFC §M1): AlgorithmDesigner 출력이 있으면 prompt에 포함 — Coder는
    # 알고리즘 선택 부담을 덜고 implementation에 집중. design 없으면 legacy 동작.
    design = state.get("algorithm_design")
    if design and isinstance(design, dict):
        edge_cases = design.get("edge_cases") or []
        edge_block = "\n".join(f"- {ec}" for ec in edge_cases) if edge_cases else "(none)"
        user += (
            "\n\n## Algorithm Design (from AlgorithmDesigner)\n\n"
            f"**Name**: {design.get('name', 'unknown')}\n\n"
            f"**Complexity target**: {design.get('complexity_target', 'unknown')}\n\n"
            f"**Pseudocode**:\n```\n{design.get('pseudocode', '')}\n```\n\n"
            f"**Edge cases to handle**:\n{edge_block}\n\n"
            "Implement this algorithm. Follow the pseudocode + handle the edge cases."
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

    # R14 (Sprint 3): fanout N개 candidate 생성 (default 1, opt-in).
    # fanout=1이면 기존 단일 call path, fanout>1이면 temperature 변동으로 N
    # solution 생성. 본 PR은 구조만 — 첫 번째 candidate 채택, best 선택은 후속 PR.
    fanout = max(1, int(state.get("coder_fanout") or 1))
    temps = _temperatures(fanout)
    candidates: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    # R-coder-parse (Round 18): LLM이 가끔 fenced block 없이 응답 → ValueError.
    # graceful fallback: 모든 fanout candidate가 fail이면 coder self-loop with
    # explicit feedback (e2e crash 방지). 일부 success 시 그 candidate들로 진행.
    for temp in temps:
        chat_t = get_chat(CODER_MODEL, temperature=temp) if temp != 0.7 else chat
        resp = tracker.invoke(chat_t, messages, node="coder", state_calls=calls)
        try:
            c, b, imp, lsn = _parse_response(str(resp.content))
        except ValueError as e:
            parse_errors.append(f"temp={temp}: {e}")
            continue
        candidates.append({
            "code": c, "brute": b, "lesson": lsn,
            "temperature": temp, "impossible": imp,
        })

    if not candidates:
        # 모든 fanout candidate가 parse 실패 → coder self-loop
        joined = "; ".join(parse_errors) if parse_errors else "no candidates"
        return {
            **state,
            "llm_calls": calls,
            "feedback_message": (
                f"Coder response parse failed for all {fanout} fanout candidate(s): "
                f"{joined}. Wrap your solution in ```python ... ``` fenced block."
            ),
            "last_failed_node": "coder",
        }

    # 첫 번째 candidate 채택 (best 선택은 후속 PR — Executor가 sample 검증)
    first = candidates[0]
    code = first["code"]
    brute = first["brute"]
    impossible = first["impossible"]
    lesson = first["lesson"]

    # R13: lesson 누적 (있을 때만). 기존 list 복사 후 append — 불변성 유지.
    lessons: list[str] = list(state.get("lessons_learned") or [])
    if lesson:
        lessons.append(lesson)

    if impossible:
        return {
            **state,
            "llm_calls": calls,
            "lessons_learned": lessons,
            "candidate_solutions": candidates,
            "feedback_message": f"Coder declared IMPOSSIBLE: {impossible}",
            "last_failed_node": "architect",
        }

    result: ProblemState = {
        **state,
        "llm_calls": calls,
        "lessons_learned": lessons,
        "candidate_solutions": candidates,
        "solution_code": code,
        "feedback_message": None,
        "last_failed_node": None,
    }
    # R15: brute가 있으면 state에 저장. 없으면 기존 brute_solution_code 보존
    # (이전 cycle에서 작성한 게 있다면 그대로 — Phase C cross-check 사용).
    if brute is not None:
        result["brute_solution_code"] = brute
    return result


def _temperatures(fanout: int) -> list[float]:
    """R14: fanout N에 대해 균등 분포 temperature 리스트 반환.

    - fanout=1 → [0.7] (기존 default)
    - fanout=2 → [0.3, 1.0]
    - fanout=3 → [0.3, 0.65, 1.0]
    - fanout=N → linspace(0.3, 1.0, N)

    Coder 응답 다양성을 위해 0.3~1.0 범위로 spread.
    """
    if fanout <= 1:
        return [0.7]
    step = (1.0 - 0.3) / (fanout - 1)
    return [round(0.3 + step * i, 2) for i in range(fanout)]
