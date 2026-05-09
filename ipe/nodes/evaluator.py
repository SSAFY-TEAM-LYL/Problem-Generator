"""Evaluator node — Phase C 통과 후 calibration anchor 기반 난이도 측정.

스펙: PROJECT_SPEC.md §4.6 (The Evaluator), ARCHITECTURE.md §3.10
근거: IMPLEMENTATION_ROADMAP §1 P9.2

- 입력: problem_description, constraints, solution_code, testcases (sample)
- 참조: ``ipe.calibration.load_anchors()`` 4~8개 anchor
- 출력: difficulty_label / difficulty_reasoning / difficulty_factors /
       difficulty_calibration_anchors

reasoning에는 사용한 anchor id를 명시해야 한다 (예: "Closest to bj_1753_gold5 —
both Dijkstra-style with N up to ~20000"). 이를 통해 calibration이 사후 검증 가능.

LLM 응답 파싱 실패 시 self-loop 시그널은 set하지 않는다 (final_status 보존):
- evaluator는 검증 통과 후 마지막 단계라 retry 부담이 큼
- 측정 불가 시 difficulty_* 필드를 None으로 두고 final_status='success' 유지
"""

from __future__ import annotations

import json
from typing import Any

from ipe.calibration import load_anchors
from ipe.llm import EVALUATOR_MODEL, get_chat, parse_json_block
from ipe.nodes._history import build_history_section
from ipe.observability import LLMCallTracker
from ipe.state import LLMCallRecord, ProblemState

MAX_TESTCASE_EXCERPT = 3            # prompt에 보여줄 testcase 수
TESTCASE_FIELD_MAX_CHARS = 80       # 각 input/expected_output 표시 길이

SYSTEM_PROMPT = """You are The Evaluator — a difficulty calibrator for
competitive programming problems.

Given a verified problem (description + constraints + golden solution + testcases),
estimate its difficulty by comparing against the calibration anchors below.

Your output MUST be a JSON block with exactly these fields:
- "difficulty_label": string in the form like "Bronze V" / "Silver III" / "Gold IV" /
  "Platinum II" — match the labeling style of the anchors
- "difficulty_reasoning": one or two sentences. MUST cite the closest anchor id(s)
  explicitly (e.g., "Closest to bj_1753_gold5 — both Dijkstra with V up to 20000").
- "difficulty_factors": object {algorithm, n_max, complexity, data_structures}
- "difficulty_calibration_anchors": list of 1–3 anchor IDs you compared against
  (must be a subset of the anchor IDs provided)

Wrap the JSON in a ```json fenced block.
"""

USER_TEMPLATE = """## Problem

{problem_description}

## Constraints

{constraints}

## Golden Solution

```
{solution_code}
```

## Testcases (sample of {n_total})

{testcases_excerpt}

{anchor_block}
"""


def _build_anchor_block(anchors: list[dict[str, Any]]) -> str:
    """anchors → markdown 블록 (LLM이 비교 참조)."""
    if not anchors:
        return "## Calibration Anchors\n\n(no anchors loaded)\n"

    lines = ["## Calibration Anchors", ""]
    for a in anchors:
        aid = a.get("id", "?")
        label = a.get("label", "?")
        summary = a.get("summary", "")
        factors = a.get("factors") or {}
        lines.append(f"### {aid} — {label}")
        lines.append(f"- summary: {summary}")
        lines.append(f"- factors: {json.dumps(factors, ensure_ascii=False)}")
        lines.append("")
    return "\n".join(lines)


def _testcases_excerpt(testcases: list[dict[str, Any]]) -> str:
    """testcases 처음 N개를 한 줄씩 요약."""
    if not testcases:
        return "(no testcases)"
    out = []
    for tc in testcases[:MAX_TESTCASE_EXCERPT]:
        kind = tc.get("kind", "?")
        inp = str(tc.get("input", ""))[:TESTCASE_FIELD_MAX_CHARS].replace("\n", " ")
        expected = str(tc.get("expected_output", ""))[:TESTCASE_FIELD_MAX_CHARS].replace("\n", " ")
        out.append(f"- [{kind}] in: {inp!r} | expected: {expected!r}")
    return "\n".join(out)


def run(
    state: ProblemState,
    *,
    tracker: LLMCallTracker,
) -> ProblemState:
    """Evaluator 노드 — calibration anchor와 비교해 난이도 라벨 + reasoning 생성.

    final_status='success'는 진입 조건이며, 본 함수는 final_status를 변경하지
    않는다 (parse 실패 시에도 success 보존, difficulty_* 필드만 None).
    """
    chat = get_chat(EVALUATOR_MODEL, max_tokens=2048)
    anchors = load_anchors()
    testcases = state.get("testcases") or []

    user = USER_TEMPLATE.format(
        problem_description=state.get("problem_description", ""),
        constraints=state.get("constraints", ""),
        solution_code=state.get("solution_code", ""),
        n_total=len(testcases),
        testcases_excerpt=_testcases_excerpt(testcases),
        anchor_block=_build_anchor_block(anchors),
    )
    user += build_history_section(state, current_node="evaluator")

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    calls: list[LLMCallRecord] = list(state.get("llm_calls") or [])
    resp = tracker.invoke(chat, messages, node="evaluator", state_calls=calls)
    text = str(resp.content)

    try:
        parsed = parse_json_block(text)
    except ValueError:
        parsed = None
    if not isinstance(parsed, dict):
        # 측정 실패 — final_status는 success 유지, difficulty_* 미설정
        return {**state, "llm_calls": calls}

    label = parsed.get("difficulty_label")
    reasoning = parsed.get("difficulty_reasoning")
    factors = parsed.get("difficulty_factors")
    used_ids_raw = parsed.get("difficulty_calibration_anchors") or []
    used_ids = [str(x) for x in used_ids_raw if isinstance(x, str)]

    # used anchor id로 실제 anchor entries 매칭
    by_id = {a.get("id"): a for a in anchors if isinstance(a.get("id"), str)}
    used_anchors = [by_id[i] for i in used_ids if i in by_id]

    return {
        **state,
        "llm_calls": calls,
        "difficulty_label": str(label) if isinstance(label, str) else None,
        "difficulty_reasoning": str(reasoning) if isinstance(reasoning, str) else None,
        "difficulty_factors": dict(factors) if isinstance(factors, dict) else None,
        "difficulty_calibration_anchors": used_anchors,
    }
