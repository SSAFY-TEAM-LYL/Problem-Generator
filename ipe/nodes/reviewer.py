"""Reviewer node — M4 (v0.3.0 RFC §M4).

Coder의 solution을 별도 Reviewer LLM call로 adversarial 검토. approve → executor
진입. reject → coder retry feedback에 weaknesses 동봉.

설계:
- Reviewer 노드는 **self-loop 안 함** — Coder에 cross-route만 (rejected 시).
- 따라서 NodeRetryBudget에 reviewer 추가 안 함 (self-loop 부재 = budget 불필요).
- Coder 측 budget이 reviewer rejection cycle도 흡수.

입력 (state):
- problem_description, constraints, sample_testcases
- solution_code (Coder 산출물)
- algorithm_design (선택, M1 산출물)
- target_language

출력 (state):
- review_status: "approved" | "rejected"
- review_reasoning: 한 문장 요약
- review_weaknesses: list[str] (reject 시만 비어 있지 않음)
- feedback_message + last_failed_node: reject 시 "coder", approve 시 None

스펙: docs/rfc/v0.3.0_multi-mechanism.md §2 M4
"""

from __future__ import annotations

from typing import Any

from ipe.llm import REVIEWER_MODEL, get_chat, parse_json_block
from ipe.nodes._history import build_history_section
from ipe.observability import LLMCallTracker
from ipe.state import LLMCallRecord, ProblemState

SYSTEM_PROMPT = """You are The Reviewer — an adversarial reviewer for competitive
programming solutions.

Given a problem and a candidate solution, find **substantive** weaknesses:
- Incorrect algorithm (does it actually solve the problem?)
- Edge cases not handled (empty input, max boundary, all-equal, single-element,
  disconnected graph, integer overflow, off-by-one, etc.)
- Complexity issues (will it TLE on the max constraint?)
- IO issues (wrong format, missing buffered IO for large input)

Output a SINGLE JSON object wrapped in ```json fence:

{
  "verdict": "approve" | "reject",
  "reasoning": "one-sentence summary",
  "weaknesses": ["specific weakness 1", "specific weakness 2", ...]
}

Decision rules:
- **approve**: Solution looks correct + covers visible edge cases. Minor style
  issues are NOT reject reasons.
- **reject**: ONE OR MORE of these is true:
  - You found a concrete failing input (state it: "fails on N=1 with X=0")
  - Algorithm is clearly wrong / off-by-one
  - Missing IO optimization for large N (will TLE)
  - Required edge case demonstrably not covered

Be **specific** in weaknesses — vague concerns ("could be slow", "maybe overflow")
are not actionable. State the concrete input + symptom.

If unsure (could go either way) → approve. Executor sample run + Phase B/C
adversarial inputs will catch real bugs. Reject should be a strong signal.
"""

USER_TEMPLATE = """## Problem

{problem_description}

## Constraints

{constraints}

## Sample Test Cases

{sample_block}

## Algorithm Design (from AlgorithmDesigner)

{design_block}

## Candidate Solution ({language})

```{language}
{solution_code}
```

Review the solution. Output JSON with verdict + reasoning + weaknesses list.
"""

FEEDBACK_SUFFIX = """

## Prior Review History

{feedback}

Consider this when deciding — if Coder already addressed prior weaknesses, that
counts toward approval. Don't recycle weaknesses that have been fixed.
"""


def _format_samples(samples: list[dict[str, Any]]) -> str:
    """sample_testcases → markdown block for prompt."""
    if not samples:
        return "(no samples)"
    parts: list[str] = []
    for i, tc in enumerate(samples[:5]):
        inp = str(tc.get("input", ""))[:200]
        out = str(tc.get("expected_output", ""))[:200]
        parts.append(
            f"### Sample {i + 1}\nInput:\n```\n{inp}\n```\nExpected:\n```\n{out}\n```"
        )
    return "\n\n".join(parts)


def _format_design(design: dict[str, Any] | None) -> str:
    """algorithm_design → markdown block. 없으면 placeholder."""
    if not design or not isinstance(design, dict):
        return "(no design — Reviewer infers algorithm from solution code itself)"
    edges = design.get("edge_cases") or []
    edge_block = (
        "\n".join(f"- {ec}" for ec in edges) if isinstance(edges, list) and edges
        else "(none specified)"
    )
    return (
        f"**Name**: {design.get('name', 'unknown')}\n\n"
        f"**Complexity target**: {design.get('complexity_target', 'unknown')}\n\n"
        f"**Pseudocode**:\n```\n{design.get('pseudocode', '')}\n```\n\n"
        f"**Edge cases required**:\n{edge_block}"
    )


def _approve(
    state: ProblemState,
    calls: list[LLMCallRecord],
    reasoning: str,
) -> ProblemState:
    """approve → executor 진입. feedback/last_failed_node를 None으로 clear."""
    return {
        **state,
        "llm_calls": calls,
        "review_status": "approved",
        "review_reasoning": reasoning,
        "review_weaknesses": [],
        "feedback_message": None,
        "last_failed_node": None,
    }


def _reject(
    state: ProblemState,
    calls: list[LLMCallRecord],
    reasoning: str,
    weaknesses: list[str],
) -> ProblemState:
    """reject → coder retry. weaknesses를 feedback_message로 동봉."""
    weakness_block = (
        "\n".join(f"- {w}" for w in weaknesses) if weaknesses
        else "(no specific weaknesses listed)"
    )
    feedback = (
        f"Reviewer rejected: {reasoning}\n\nWeaknesses to address:\n{weakness_block}\n\n"
        "Rewrite the solution to fix these specific issues."
    )
    return {
        **state,
        "llm_calls": calls,
        "review_status": "rejected",
        "review_reasoning": reasoning,
        "review_weaknesses": weaknesses,
        "feedback_message": feedback,
        "last_failed_node": "coder",
    }


def run(
    state: ProblemState,
    *,
    tracker: LLMCallTracker,
) -> ProblemState:
    """Reviewer 노드 — Coder solution → approve/reject 판정.

    invalid state (solution_code 없음) 시: 보수적 reject (Coder가 빈 응답 → 다시).
    parse 실패 시: graceful approve (Executor가 최종 검증).

    너무 strict하면 coder budget 소진 — Opus + "if unsure approve" prompt로 완화.
    """
    solution = state.get("solution_code")
    calls: list[LLMCallRecord] = list(state.get("llm_calls") or [])

    if not solution:
        # state invariant 깨짐 — Coder가 solution 없이 reviewer로 오면 안 됨.
        # 보수적 reject + coder retry.
        return _reject(
            state, calls,
            "No solution_code present at reviewer entry — Coder must produce a "
            "fenced code block before review.",
            ["solution_code is empty"],
        )

    language = state.get("target_language", "python")
    chat = get_chat(REVIEWER_MODEL, max_tokens=2048)

    samples = state.get("sample_testcases") or []
    design = state.get("algorithm_design")
    user = USER_TEMPLATE.format(
        problem_description=state.get("problem_description") or "",
        constraints=state.get("constraints") or "",
        sample_block=_format_samples(samples),
        design_block=_format_design(design if isinstance(design, dict) else None),
        language=language,
        solution_code=solution,
    )
    feedback = state.get("feedback_message")
    if feedback:
        user += FEEDBACK_SUFFIX.format(feedback=feedback)
    user += build_history_section(state, current_node="reviewer")

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    resp = tracker.invoke(chat, messages, node="reviewer", state_calls=calls)

    try:
        data = parse_json_block(str(resp.content))
    except ValueError as e:
        # 보수적 fallback — parse 실패해도 graceful approve (executor가 잡음).
        # 매번 parse fail로 reject하면 coder budget 소진 위험.
        return _approve(
            state, calls,
            f"Reviewer response unparseable ({e}) — graceful approve, deferring to Executor.",
        )

    if not isinstance(data, dict):
        return _approve(
            state, calls,
            "Reviewer output not a JSON object — graceful approve.",
        )

    verdict = str(data.get("verdict", "")).strip().lower()
    reasoning = str(data.get("reasoning") or "(no reasoning provided)")
    raw_weaknesses = data.get("weaknesses") or []
    weaknesses: list[str] = (
        [str(w) for w in raw_weaknesses] if isinstance(raw_weaknesses, list) else []
    )

    if verdict == "approve":
        return _approve(state, calls, reasoning)
    if verdict == "reject":
        return _reject(state, calls, reasoning, weaknesses)

    # 알 수 없는 verdict — graceful approve (보수적 reject보다 budget 보호).
    return _approve(
        state, calls,
        f"Reviewer verdict '{verdict}' unrecognized — graceful approve.",
    )
