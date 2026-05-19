"""통합 테스트 공용 mock helpers (P8 audit C1 통합).

스펙: ``tests/integration/test_routing.py`` / ``test_resume.py`` / ``test_replay.py``
3개 파일이 동일한 mock helpers를 복제 보유 (~420줄 DRY 위반) → 본 모듈로 통합.

P9 evaluator 통합 테스트도 같은 helpers를 재사용할 수 있다.

제공:
- chat mock 빌더: ``make_chat`` / ``patch_chat`` / ``patch_chat_raises`` /
  ``make_chat_forbid_invoke`` / ``patch_forbid``
- 응답 빌더: ``arch_response`` / ``adv_response``
- 상수: ``VALID_SAMPLES`` / ``VALID_CODER`` / ``BAD_CODER`` / ``VALID_ADV`` /
  ``GEN_RESPONSE``
- 상태 빌더: ``default_budget`` / ``initial_state``
- wiring: ``wire_all_chats_normal`` / ``wire_all_chats_forbid_invoke``
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.state import ProblemState


def make_chat(content: str, *, in_tok: int = 0, out_tok: int = 0) -> MagicMock:
    """LLM chat mock — usage_metadata로 cost 시뮬.

    in_tok/out_tok이 크면 ``_cost_usd``가 큰 값을 반환하여 cost_exceeded 가드 검증 가능.
    """
    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    chat.temperature = None
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": in_tok, "output_tokens": out_tok}
    chat.invoke.return_value = resp
    return chat


def patch_chat(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    content: str,
    *,
    in_tok: int = 0,
    out_tok: int = 0,
) -> None:
    """``target`` (예: ``ipe.nodes.architect.get_chat``)을 mock chat factory로 swap."""
    monkeypatch.setattr(
        target, lambda *a, **k: make_chat(content, in_tok=in_tok, out_tok=out_tok)
    )


def patch_chat_raises(
    monkeypatch: pytest.MonkeyPatch, target: str, exc: Exception
) -> None:
    """target.get_chat이 chat을 반환하되, chat.invoke 호출 시 ``exc`` 발생."""
    def factory(*a: Any, **k: Any) -> MagicMock:
        chat = MagicMock()
        chat.model = "claude-opus-4-7"
        chat.temperature = None
        chat.invoke.side_effect = exc
        return chat
    monkeypatch.setattr(target, factory)


def make_chat_forbid_invoke() -> MagicMock:
    """LLM이 호출되면 즉시 fail — replay 검증용."""
    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    chat.temperature = None
    chat.invoke.side_effect = AssertionError(
        "chat.invoke must NOT be called during replay"
    )
    return chat


def patch_forbid(monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    monkeypatch.setattr(target, lambda *a, **k: make_chat_forbid_invoke())


def arch_response(samples: list[dict[str, Any]]) -> str:
    """Architect 정상 응답 — 펜스 안 JSON (A+B 문제)."""
    body = {
        "problem_title": "A+B",
        "problem_description": "Read two integers and print their sum.",
        "constraints": "1 <= a, b <= 1e9",
        "constraints_structured": {
            "variables": [
                {"name": "a", "min": 1, "max": 10**9, "type": "int"},
                {"name": "b", "min": 1, "max": 10**9, "type": "int"},
            ],
            "time_limit_ms": 2000,
            "memory_limit_mb": 256,
        },
        "sample_testcases": samples,
        "has_special_judge": False,
    }
    return f"```json\n{json.dumps(body)}\n```"


def adv_response(inputs: list[dict[str, Any]]) -> str:
    """Auditor 정상 응답 — 펜스 안 JSON (adversarial_inputs)."""
    return f"```json\n{json.dumps({'adversarial_inputs': inputs})}\n```"


VALID_SAMPLES: list[dict[str, Any]] = [
    {"input": "1 2\n", "expected_output": "3"},
    {"input": "10 20\n", "expected_output": "30"},
    {"input": "5 7\n", "expected_output": "12"},
]
VALID_CODER = "```python\na, b = map(int, input().split())\nprint(a + b)\n```"
BAD_CODER = "```python\nprint(0)\n```"

VALID_ADV: list[dict[str, Any]] = [
    {"input": "1 1\n", "category": "MIN", "reason": "smallest"},
    {"input": "1000000000 1000000000\n", "category": "MAX", "reason": "max"},
    {"input": "1 1000000000\n", "category": "BOUNDARY", "reason": "low+high"},
    {"input": "5 5\n", "category": "UNIFORM", "reason": "equal"},
    {"input": "100 200\n", "category": "ADV", "reason": "regular"},
    {"input": "999999999 1\n", "category": "BOUNDARY", "reason": "near max"},
    {"input": "2 3\n", "category": "MIN", "reason": "near min"},
    {"input": "500 500\n", "category": "UNIFORM", "reason": "midrange"},
]

# Evaluator mock — Bronze V (A+B에 가장 가까운 anchor)
EVAL_RESPONSE = """```json
{
  "difficulty_label": "Bronze V",
  "difficulty_reasoning": "Closest to bj_1000_bronze5 — both A+B style with O(1) implementation.",
  "difficulty_factors": {
    "algorithm": "implementation",
    "n_max": 1,
    "complexity": "O(1)",
    "data_structures": []
  },
  "difficulty_calibration_anchors": ["bj_1000_bronze5"]
}
```"""


# Generator mock: _BLOCK_RE 형식 3개 (NAME/CATEGORY/DESCRIPTION + ```python fence```)
GEN_RESPONSE = """NAME: gen_small
CATEGORY: RANDOM_SMALL
DESCRIPTION: small random a+b
```python
import sys, random
seed = int(sys.argv[1])
random.seed(seed)
print(f"{random.randint(1, 100)} {random.randint(1, 100)}")
```

NAME: gen_medium
CATEGORY: RANDOM_MEDIUM
DESCRIPTION: medium values
```python
import sys
seed = int(sys.argv[1])
print(f"{seed * 1000} {seed * 2000}")
```

NAME: gen_max
CATEGORY: MAX_STRESS
DESCRIPTION: large fixed values
```python
import sys
seed = int(sys.argv[1])
print(f"{500000000 + seed} {500000000 + seed}")
```
"""


# M1 (v0.3.0 RFC §M1): AlgorithmDesigner mock 응답 — A+B problem의 algorithm.
DESIGNER_RESPONSE = """```json
{
  "name": "Addition",
  "pseudocode": "1. Read two integers a, b from stdin\\n2. Print a+b",
  "complexity_target": "Time O(1), Space O(1)",
  "edge_cases": ["a=0", "b=0", "very large values near 1e9"]
}
```"""


def default_budget() -> dict[str, int]:
    """SPEC §5 default node_retry_budget. M1 (Round 21): algorithm_designer 추가."""
    return {
        "architect": 2,
        "algorithm_designer": 2,
        "coder": 4,
        "auditor": 2,
        "generator": 2,
    }


def initial_state(
    *,
    max_iter: int = 5,
    max_cost_usd: float = 100.0,
    budget: dict[str, int] | None = None,
) -> ProblemState:
    """A+B 문제 + budget 기본값으로 새 ProblemState 빌드."""
    return {
        "target_algorithm": "A+B",
        "target_language": "python",
        "iteration_count": 0,
        "max_iter": max_iter,
        "max_cost_usd": max_cost_usd,
        "node_retry_budget": (budget or default_budget()),  # type: ignore[typeddict-item]
        "iteration_history": [],
        "llm_calls": [],
    }


def wire_all_chats_normal(
    monkeypatch: pytest.MonkeyPatch,
    *,
    coder_response: str = VALID_CODER,
    in_tok: int = 0,
    out_tok: int = 0,
) -> None:
    """모든 LLM 노드 정상 응답 mock — M1 (Round 21) 후 algorithm_designer 포함 6 노드."""
    patch_chat(monkeypatch, "ipe.nodes.architect.get_chat",
               arch_response(VALID_SAMPLES), in_tok=in_tok, out_tok=out_tok)
    patch_chat(monkeypatch, "ipe.nodes.algorithm_designer.get_chat",
               DESIGNER_RESPONSE, in_tok=in_tok, out_tok=out_tok)
    patch_chat(monkeypatch, "ipe.nodes.coder.get_chat", coder_response,
               in_tok=in_tok, out_tok=out_tok)
    patch_chat(monkeypatch, "ipe.nodes.auditor.get_chat",
               adv_response(VALID_ADV), in_tok=in_tok, out_tok=out_tok)
    patch_chat(monkeypatch, "ipe.nodes.generator.get_chat", GEN_RESPONSE,
               in_tok=in_tok, out_tok=out_tok)
    patch_chat(monkeypatch, "ipe.nodes.evaluator.get_chat", EVAL_RESPONSE,
               in_tok=in_tok, out_tok=out_tok)


def wire_all_chats_forbid_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """모든 노드의 chat.invoke를 금지 — ReplayTracker가 우회해야 PASS.
    M1 (Round 21): algorithm_designer 포함 6 노드."""
    for node in ("architect", "algorithm_designer", "coder", "auditor", "generator", "evaluator"):
        patch_forbid(monkeypatch, f"ipe.nodes.{node}.get_chat")
