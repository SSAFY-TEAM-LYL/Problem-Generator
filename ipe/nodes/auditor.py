"""Auditor node — adversarial 작은 엣지케이스 생성.

스펙: PROJECT_SPEC.md §4.3 (The Auditor), ARCHITECTURE.md §3.7

- 입력: problem_description, constraints, solution_code (+ feedback_message)
- 출력: ``adversarial_inputs: list[{input, category, reason}]``
- 8개 미만 시 self-loop (``last_failed_node='auditor'``)
- ``expected_output``은 생성하지 않음 — Executor가 솔루션을 oracle로 사용해 채움.
- truncation 복구 — LLM 응답이 max_tokens에 걸려 잘렸으면 완성된 entry만 살림.
"""

from __future__ import annotations

from typing import Any

from ipe.llm import AUDITOR_MODEL, get_chat, parse_json_array_field, parse_json_block
from ipe.nodes._history import build_history_section
from ipe.observability import LLMCallTracker
from ipe.state import LLMCallRecord, ProblemState

MIN_ADVERSARIAL_CASES = 8
MAX_ADVERSARIAL_CASES = 15

SYSTEM_PROMPT = """You are The Auditor — an adversarial test case designer.

Given a problem and its golden solution, design 8–15 SMALL adversarial test cases
that target potential bugs and corner cases. Each input must be ≤200 chars.

Categories (use one per case):
- MIN_SIZE: smallest valid N
- SINGLE_ELEMENT: array of length 1
- UNIFORM: all elements equal
- BOUNDARY_LOW: minimum constraint values
- BOUNDARY_HIGH: maximum constraint values (within ≤200 chars)
- SORTED_ASC / SORTED_DESC: pre-sorted input
- DEGENERATE: empty graph, no edges, self-loops, etc.
- NUMERICAL_EDGE: zero, negative, max int, overflow trigger
- ADVERSARIAL: tricky case the author likely missed

Do NOT include ``expected_output`` — the Executor will use the golden solution
itself as the oracle to populate it.

Output JSON wrapped in a ```json fence:

{
  "adversarial_inputs": [
    {"input": "...", "category": "MIN_SIZE", "reason": "..."},
    ...
  ]
}

Each entry MUST have ``input`` (string). ``category`` and ``reason`` are recommended.
"""

USER_TEMPLATE = """## Problem

{problem_description}

## Constraints

{constraints}

## Golden Solution

```
{solution_code}
```

Generate 8–15 adversarial test cases. Each input must respect the constraints.
"""

FEEDBACK_SUFFIX = """

## Previous Failure Feedback

{feedback}

이전 시도와 다른 카테고리/접근법을 사용하라 (REVIEW W4: oscillation 방지).
"""


def _route_back(
    state: ProblemState, calls: list[LLMCallRecord], reason: str
) -> ProblemState:
    """auditor self-loop으로 라우팅."""
    return {
        **state,
        "llm_calls": calls,
        "feedback_message": reason,
        "last_failed_node": "auditor",
    }


def _normalize_entry(it: Any) -> dict[str, Any] | None:
    """단일 entry를 정상 형식으로 변환. ``input`` 누락 시 None."""
    if not isinstance(it, dict):
        return None
    if "input" not in it:
        return None
    return {
        "input": str(it["input"]),
        "category": str(it.get("category", "ADVERSARIAL")),
        "reason": str(it.get("reason", "")),
    }


def run(
    state: ProblemState,
    *,
    tracker: LLMCallTracker,
) -> ProblemState:
    """Auditor 노드 — adversarial inputs 8~15개 생성."""
    chat = get_chat(AUDITOR_MODEL, max_tokens=4096)
    user = USER_TEMPLATE.format(
        problem_description=state.get("problem_description", ""),
        constraints=state.get("constraints", ""),
        solution_code=state.get("solution_code", ""),
    )
    feedback = state.get("feedback_message")
    if feedback:
        user += FEEDBACK_SUFFIX.format(feedback=feedback)
    user += build_history_section(state, current_node="auditor")

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    calls: list[LLMCallRecord] = list(state.get("llm_calls") or [])
    resp = tracker.invoke(chat, messages, node="auditor", state_calls=calls)
    text = str(resp.content)

    # 1차: 정상 JSON 파싱
    inputs: list[Any] = []
    try:
        data = parse_json_block(text)
        if isinstance(data, dict) and isinstance(data.get("adversarial_inputs"), list):
            inputs = data["adversarial_inputs"]
        elif isinstance(data, list):
            inputs = data
    except ValueError:
        # 2차: truncation 복구 — 완성된 entry만 살림
        inputs = parse_json_array_field(text, "adversarial_inputs")

    # 각 entry 형식 정규화
    valid: list[dict[str, Any]] = []
    for it in inputs:
        norm = _normalize_entry(it)
        if norm is not None:
            valid.append(norm)

    if len(valid) < MIN_ADVERSARIAL_CASES:
        return _route_back(
            state,
            calls,
            f"auditor: only {len(valid)} valid cases, need >= {MIN_ADVERSARIAL_CASES}",
        )

    # 상한 초과 시 앞부분만 채택
    return {
        **state,
        "llm_calls": calls,
        "adversarial_inputs": valid[:MAX_ADVERSARIAL_CASES],
        "feedback_message": None,
        "last_failed_node": None,
    }
