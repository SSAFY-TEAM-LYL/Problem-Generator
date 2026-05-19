"""Architect node — target_algorithm으로부터 문제 설계.

스펙: PROJECT_SPEC.md §4.1 (The Architect), ARCHITECTURE.md §3.5

- 입력: target_algorithm (+ feedback_message)
- 출력: problem_title, problem_description, constraints (raw), constraints_structured,
       sample_testcases (3+개, N ≤ 5), has_special_judge
- 검증: constraints_structured 형식 강제 (jsonschema 대신 인라인 validator).
       위반 시 self-loop (last_failed_node='architect').

M3 (v0.3.0 RFC §M3): Multi-model consensus. Opus + Sonnet 순차 호출 → 둘 다 valid +
structural match면 Opus 채택, 한쪽만 valid면 graceful (그 모델 채택), 둘 다 valid
인데 구조 불일치면 architect retry (둘 다 의심), 둘 다 invalid면 retry.
state.architect_candidates에 두 응답 모두 저장 (분석/관측).
"""

from __future__ import annotations

from typing import Any

from ipe.llm import (
    ARCHITECT_MODEL,
    CONSENSUS_MODEL,
    get_chat,
    parse_json_block,
)
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

    M3: 두 모델 호출의 공통 검증 로직 — 분기마다 try/except 복제 회피.
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


def _structural_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """M3 consensus 판정: 두 architect 응답의 구조 일치 여부.

    일치 조건 (모두 충족):
    - constraints_structured.time_limit_ms 같음
    - constraints_structured.memory_limit_mb 같음
    - variables 개수 같음 + 정렬된 name 집합 같음
    - sample_testcases 개수 같음

    제목/설명/sample 값은 비교 X — 자연어 표현은 모델마다 달라도 정상.
    구조적 핵심 (time/memory/variable shape/sample count)만 합의 신호로 사용.
    """
    cs_a = a.get("constraints_structured") or {}
    cs_b = b.get("constraints_structured") or {}
    if not (isinstance(cs_a, dict) and isinstance(cs_b, dict)):
        return False
    if cs_a.get("time_limit_ms") != cs_b.get("time_limit_ms"):
        return False
    if cs_a.get("memory_limit_mb") != cs_b.get("memory_limit_mb"):
        return False

    vars_a = cs_a.get("variables") or []
    vars_b = cs_b.get("variables") or []
    if not (isinstance(vars_a, list) and isinstance(vars_b, list)):
        return False
    if len(vars_a) != len(vars_b):
        return False
    names_a = sorted(str(v.get("name", "")) for v in vars_a if isinstance(v, dict))
    names_b = sorted(str(v.get("name", "")) for v in vars_b if isinstance(v, dict))
    if names_a != names_b:
        return False

    samples_a = a.get("sample_testcases") or []
    samples_b = b.get("sample_testcases") or []
    return len(samples_a) == len(samples_b)


def _summarize(d: dict[str, Any]) -> str:
    """M3 consensus 불일치 feedback용 한 줄 요약."""
    cs = d.get("constraints_structured") or {}
    if not isinstance(cs, dict):
        cs = {}
    vars_list = cs.get("variables") or []
    samples = d.get("sample_testcases") or []
    return (
        f"tl={cs.get('time_limit_ms')}ms ml={cs.get('memory_limit_mb')}MB "
        f"vars={len(vars_list) if isinstance(vars_list, list) else '?'} "
        f"samples={len(samples) if isinstance(samples, list) else '?'}"
    )


def _route_back(
    state: ProblemState,
    calls: list[LLMCallRecord],
    reason: str,
    candidates: list[dict[str, Any]] | None = None,
) -> ProblemState:
    """architect self-loop으로 라우팅. M3: candidates 저장 (분석용)."""
    out: ProblemState = {
        **state,
        "llm_calls": calls,
        "feedback_message": reason,
        "last_failed_node": "architect",
    }
    if candidates is not None:
        out["architect_candidates"] = candidates
    return out


def run(
    state: ProblemState,
    *,
    tracker: LLMCallTracker,
) -> ProblemState:
    """Architect 노드 — algorithm → 문제 + constraints + samples 생성.

    M3 (v0.3.0 RFC §M3): Opus + Sonnet 순차 호출 후 structural consensus voting.
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

    # M3: 순차 호출 (LLMCallTracker.seq race 회피 + trace 순서 보장).
    chat_opus = get_chat(ARCHITECT_MODEL, max_tokens=4096)
    chat_sonnet = get_chat(CONSENSUS_MODEL, max_tokens=4096)

    resp_opus = tracker.invoke(chat_opus, messages, node="architect", state_calls=calls)
    resp_sonnet = tracker.invoke(chat_sonnet, messages, node="architect", state_calls=calls)

    opus_data, opus_err = _parse_and_validate(str(resp_opus.content))
    sonnet_data, sonnet_err = _parse_and_validate(str(resp_sonnet.content))

    # state.architect_candidates에 valid한 것들만 저장 (분석/관측).
    candidates: list[dict[str, Any]] = []
    if opus_data is not None:
        candidates.append(opus_data)
    if sonnet_data is not None:
        candidates.append(sonnet_data)

    # 경로 결정:
    # 1) 둘 다 invalid → architect retry
    # 2) Opus만 valid → opus_only graceful 채택
    # 3) Sonnet만 valid → sonnet_only graceful 채택
    # 4) 둘 다 valid + structural match → match (Opus 채택)
    # 5) 둘 다 valid + structural diff → architect retry (consensus 실패)
    if opus_data is None and sonnet_data is None:
        return _route_back(
            state,
            calls,
            (
                "M3 multi-model: both Opus and Sonnet architects failed validation. "
                f"Opus: {opus_err}. Sonnet: {sonnet_err}."
            ),
            candidates,
        )

    chosen: dict[str, Any]
    consensus: str
    if opus_data is None:
        assert sonnet_data is not None  # for mypy
        chosen = sonnet_data
        consensus = "sonnet_only"
    elif sonnet_data is None:
        chosen = opus_data
        consensus = "opus_only"
    else:
        if _structural_match(opus_data, sonnet_data):
            chosen = opus_data
            consensus = "match"
        else:
            return _route_back(
                state,
                calls,
                (
                    "M3 multi-model: Opus and Sonnet architects disagree on structure. "
                    f"Opus[{_summarize(opus_data)}] vs Sonnet[{_summarize(sonnet_data)}]. "
                    "Re-design so the structural shape (time/memory/variable count/sample "
                    "count) is unambiguous from the problem statement."
                ),
                candidates,
            )

    return {
        **state,
        "llm_calls": calls,
        "problem_title": str(chosen["problem_title"]),
        "problem_description": str(chosen["problem_description"]),
        "constraints": str(chosen["constraints"]),
        "constraints_structured": chosen["constraints_structured"],
        "sample_testcases": chosen["sample_testcases"],
        "has_special_judge": bool(chosen.get("has_special_judge", False)),
        "architect_candidates": candidates,
        "architect_consensus": consensus,
        "feedback_message": None,
        "last_failed_node": None,
    }
