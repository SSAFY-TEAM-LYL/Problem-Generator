"""Architect node — target_algorithm으로부터 문제 설계.

스펙: docs/SPEC.md FR-1, docs/ARCHITECTURE.md §3.5

- 입력: target_algorithm (+ feedback_message)
- 출력: problem_title, problem_description, constraints (raw), constraints_structured,
       sample_testcases (3+개, N ≤ 5), has_special_judge
- 검증: constraints_structured 형식 강제 (jsonschema 대신 인라인 validator).
       위반 시 self-loop (last_failed_node='architect').

v0.3.0-rc1 M3 rollback (2026-05-21): A/B 측정 결과 M3 dual-call 의 net effect 가
0 ~ 음 (Dijkstra baseline 3/3 vs IPE-with-M3 0/3, sample-level -5.2pp,
oscillation_break +34). single Opus call 로 복귀. 자세한 내용은
`docs/improvements/multi-mechanism.md` (또는 archive 의 v0.3.0 RFC §M3).
"""

from __future__ import annotations

from typing import Any

from ipe.llm import ARCHITECT_MODEL, get_chat, parse_json_block
from ipe.nodes._history import build_history_section
from ipe.observability import LLMCallTracker
from ipe.state import LLMCallRecord, ProblemState

SYSTEM_PROMPT = """You are The Architect — a master problem designer for competitive programming.

Given a target algorithm category, design a NEW problem that:
- Has a unique storytelling/setting (not a clone of standard textbook problems)
- Has clear, unambiguous constraints
- Has 3–5 small sample test cases (N ≤ 5) with hand-verifiable expected outputs
- Has a logical relationship between input size and time/memory limits

Output a SINGLE JSON object with the following structure (wrap in ```json fence):

{
  "problem_title": "...",
  "problem_description": "Markdown body of the problem (Korean OK)",
  "constraints": "1 ≤ N ≤ 100,000, 시간 2초, 메모리 256MB",
  "constraints_structured": {
    "variables": [{"name": "N", "min": 1, "max": 100000, "type": "int"}],
    "time_limit_ms": 2000,
    "memory_limit_mb": 256
  },
  "sample_testcases": [
    {"input": "...", "expected_output": "...", "note": "1-line solving hint"}
  ],
  "has_special_judge": false
}

Required keys: problem_title, problem_description, constraints, constraints_structured,
sample_testcases (>= 3 items). has_special_judge defaults to false.

Do NOT specify difficulty — it will be evaluated post-verification by a separate node.
"""

USER_TEMPLATE = """## Target Algorithm

{algorithm}

Design a problem that exercises this algorithm.
"""

FEEDBACK_SUFFIX = """

## Previous Failure Feedback

{feedback}

이전 시도와 다른 접근/문제를 설계하라 (REVIEW W4: oscillation 방지).
"""


class ConstraintValidationError(ValueError):
    """constraints_structured 형식 위반."""


def _validate_constraints_structured(cs: Any) -> None:
    """SPEC §2 ConstraintSpec 형식 강제 검증.

    Required: ``time_limit_ms`` (int), ``memory_limit_mb`` (int).
    Optional: ``variables`` (list of ``{name, min, max[, type]}``).
    """
    if not isinstance(cs, dict):
        raise ConstraintValidationError("constraints_structured must be an object")
    if "time_limit_ms" not in cs:
        raise ConstraintValidationError("constraints_structured.time_limit_ms required")
    if not isinstance(cs["time_limit_ms"], int):
        raise ConstraintValidationError("constraints_structured.time_limit_ms must be int")
    if "memory_limit_mb" not in cs:
        raise ConstraintValidationError("constraints_structured.memory_limit_mb required")
    if not isinstance(cs["memory_limit_mb"], int):
        raise ConstraintValidationError("constraints_structured.memory_limit_mb must be int")
    if "variables" in cs:
        variables = cs["variables"]
        if not isinstance(variables, list):
            raise ConstraintValidationError("variables must be a list")
        for v in variables:
            if not isinstance(v, dict):
                raise ConstraintValidationError("variables[] entries must be objects")
            for key in ("name", "min", "max"):
                if key not in v:
                    raise ConstraintValidationError(
                        f"variables[] missing required field: {key}"
                    )


def _parse_and_validate(content: str) -> tuple[dict[str, Any] | None, str | None]:
    """LLM 응답 1건을 parse + 형식 검증. 성공 시 ``(data, None)``, 실패 시 ``(None, reason)``.

    M3 dual-call rollback (2026-05-21) 후 single Opus call 에서도 동일 검증 사용.
    """
    try:
        data = parse_json_block(content)
    except ValueError as e:
        return None, f"JSON parse error: {e}"

    if not isinstance(data, dict):
        return None, "output is not a JSON object"

    required = (
        "problem_title",
        "problem_description",
        "constraints",
        "constraints_structured",
        "sample_testcases",
    )
    missing = [k for k in required if k not in data]
    if missing:
        return None, f"missing fields: {missing}"

    samples = data["sample_testcases"]
    if not isinstance(samples, list) or len(samples) < 3:
        n = len(samples) if isinstance(samples, list) else "invalid"
        return None, f"too few sample_testcases: {n}"

    try:
        _validate_constraints_structured(data["constraints_structured"])
    except ConstraintValidationError as e:
        return None, f"constraints_structured invalid: {e}"

    return data, None


def _route_back(
    state: ProblemState, calls: list[LLMCallRecord], reason: str
) -> ProblemState:
    """architect self-loop으로 라우팅."""
    return {
        **state,
        "llm_calls": calls,
        "feedback_message": reason,
        "last_failed_node": "architect",
    }


def run(
    state: ProblemState,
    *,
    tracker: LLMCallTracker,
) -> ProblemState:
    """Architect 노드 — algorithm → 문제 + constraints + samples 생성.

    v0.3.0-rc1 M3 rollback (2026-05-21): single Opus call. M3 dual-call 의
    net effect 가 0 ~ 음으로 측정 — Dijkstra baseline 3/3 vs IPE 0/3, sample
    -5.2pp, oscillation_break +34 events. 자세한 내용은 measurement 보고서.
    """
    user = USER_TEMPLATE.format(algorithm=state.get("target_algorithm", ""))
    feedback = state.get("feedback_message")
    if feedback:
        user += FEEDBACK_SUFFIX.format(feedback=feedback)
    user += build_history_section(state, current_node="architect")

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    calls: list[LLMCallRecord] = list(state.get("llm_calls") or [])

    chat = get_chat(ARCHITECT_MODEL, max_tokens=4096)
    resp = tracker.invoke(chat, messages, node="architect", state_calls=calls)

    data, err = _parse_and_validate(str(resp.content))
    if data is None:
        return _route_back(state, calls, f"Architect failed validation: {err}")

    return {
        **state,
        "llm_calls": calls,
        "problem_title": str(data["problem_title"]),
        "problem_description": str(data["problem_description"]),
        "constraints": str(data["constraints"]),
        "constraints_structured": data["constraints_structured"],
        "sample_testcases": data["sample_testcases"],
        "has_special_judge": bool(data.get("has_special_judge", False)),
        "feedback_message": None,
        "last_failed_node": None,
    }
