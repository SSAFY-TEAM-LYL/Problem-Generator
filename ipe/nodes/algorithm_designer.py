"""Algorithm Designer node — M1 (v0.3.0 RFC §M1).

Coder를 두 단계로 분해: AlgorithmDesigner (이 노드) → Coder (Implementer).
ECC subagent 패턴 — 책임 분리로 quality 개선.

입력:
- problem_description, constraints, sample_testcases (Architect 출력)

출력 (state.algorithm_design):
- name: str — 알고리즘 이름 (e.g. "BFS shortest path", "Segment Tree")
- pseudocode: str — 단계별 의사코드 (markdown)
- complexity_target: str — 목표 복잡도 (e.g. "O(V + E)")
- edge_cases: list[str] — Implementer가 처리해야 할 edge case 리스트

다음 노드 (Coder)가 이 정보를 prompt에 포함하여 구현 quality ↑.

스펙: docs/rfc/v0.3.0_multi-mechanism.md §2 M1
"""

from __future__ import annotations

from typing import Any

from ipe.llm import DESIGNER_MODEL, get_chat, parse_json_block
from ipe.nodes._history import build_history_section
from ipe.observability import LLMCallTracker
from ipe.state import LLMCallRecord, ProblemState

SYSTEM_PROMPT = """You are The Algorithm Designer — a master algorithm strategist.

Given a problem statement, constraints, and sample testcases, decide:
1. **Algorithm name**: e.g. "BFS shortest path", "Segment Tree", "DP — LIS"
2. **Pseudocode**: language-agnostic step-by-step (markdown numbered list, 5-15 lines)
3. **Complexity target**: Big-O for both time and space (e.g. "Time O(N log N), Space O(N)")
4. **Edge cases**: 3-7 specific cases the implementer must handle
   (e.g. "N=1", "all elements equal", "graph disconnected")

Output a SINGLE JSON object wrapped in ```json fence:

{
  "name": "algorithm name",
  "pseudocode": "1. Initialize ...\\n2. For each ...\\n...",
  "complexity_target": "Time O(...), Space O(...)",
  "edge_cases": ["case 1", "case 2", ...]
}

Constraints on output:
- Be **concise**. Pseudocode 5-15 lines max.
- edge_cases 3-7 items, each one short phrase.
- DO NOT write actual code — that's the Implementer's job in the next stage.
- Choose the algorithm that **best fits the time/memory constraints**. If N=200000 and
  time_limit=2s, O(N^2) is wrong; pick O(N log N) or O(N).
"""

USER_TEMPLATE = """## Problem

{problem_description}

## Constraints

{constraints}

## Sample Testcases

{sample_block}

Design the algorithm.
"""

FEEDBACK_SUFFIX = """

## Previous Failure Feedback

{feedback}

이전 시도와 다른 algorithm 또는 더 효율적인 접근을 고려하라.
"""


def _format_samples(samples: list[dict[str, Any]]) -> str:
    """sample_testcases → markdown block for prompt."""
    if not samples:
        return "(no samples)"
    parts: list[str] = []
    for i, tc in enumerate(samples[:5]):
        inp = str(tc.get("input", ""))[:200]
        out = str(tc.get("expected_output", ""))[:200]
        parts.append(f"### Sample {i + 1}\nInput:\n```\n{inp}\n```\nExpected:\n```\n{out}\n```")
    return "\n\n".join(parts)


def _route_back(
    state: ProblemState, calls: list[LLMCallRecord], reason: str
) -> ProblemState:
    """algorithm_designer self-loop으로 라우팅 (decision이 budget 처리)."""
    return {
        **state,
        "llm_calls": calls,
        "feedback_message": reason,
        "last_failed_node": "algorithm_designer",
    }


def run(
    state: ProblemState,
    *,
    tracker: LLMCallTracker,
) -> ProblemState:
    """AlgorithmDesigner 노드 — problem → algorithm name + pseudocode + complexity + edge_cases."""
    chat = get_chat(DESIGNER_MODEL, max_tokens=2048, temperature=0.3)

    samples = state.get("sample_testcases") or []
    user = USER_TEMPLATE.format(
        problem_description=state.get("problem_description") or "",
        constraints=state.get("constraints") or "",
        sample_block=_format_samples(samples),
    )
    feedback = state.get("feedback_message")
    if feedback:
        user += FEEDBACK_SUFFIX.format(feedback=feedback)
    user += build_history_section(state, current_node="algorithm_designer")

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    calls: list[LLMCallRecord] = list(state.get("llm_calls") or [])
    resp = tracker.invoke(chat, messages, node="algorithm_designer", state_calls=calls)

    try:
        data = parse_json_block(str(resp.content))
    except ValueError as e:
        return _route_back(state, calls, f"AlgorithmDesigner JSON parse error: {e}")

    if not isinstance(data, dict):
        return _route_back(state, calls, "AlgorithmDesigner output is not a JSON object")

    required = ("name", "pseudocode", "complexity_target", "edge_cases")
    missing = [k for k in required if k not in data]
    if missing:
        return _route_back(
            state, calls, f"AlgorithmDesigner output missing fields: {missing}"
        )

    edge_cases = data["edge_cases"]
    if not isinstance(edge_cases, list):
        return _route_back(state, calls, "edge_cases must be a list of strings")

    return {
        **state,
        "llm_calls": calls,
        "algorithm_design": {
            "name": str(data["name"]),
            "pseudocode": str(data["pseudocode"]),
            "complexity_target": str(data["complexity_target"]),
            "edge_cases": [str(ec) for ec in edge_cases],
        },
        "feedback_message": None,
        "last_failed_node": None,
    }
