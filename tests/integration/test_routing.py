"""Routing 통합 테스트 — graph.invoke full cycle (P7.4).

스펙: ARCHITECTURE.md §3.4, IMPLEMENTATION_ROADMAP §1 P7.4
범위: graph.invoke를 통한 의도적 실패 사이클 — Definition of Done 4종.

단위 테스트 (``_decision``, ``_route_after_decision``, ``build_history_section``)
는 ``tests/test_routing_units.py``로 분리 (P7 audit B1, budget ≤400 준수).

시나리오:
1. happy path full cycle → ``final_status='success'`` + sample/adv/generated testcases
2. coder budget exhausted (BAD_CODER + budget=2) → ``budget_exhausted``
3. max_iter=1 + 잘못된 코드 → ``max_iterations``
4. max_cost_usd=0.01 + 10k tokens → ``cost_exceeded``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.graph import build_graph
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.state import ProblemState

# =============================================================================
# 공통 mock helpers
# =============================================================================


def _make_chat(content: str, *, in_tok: int = 0, out_tok: int = 0) -> MagicMock:
    """LLM chat mock — usage_metadata로 cost 시뮬.

    in_tok/out_tok이 크면 _cost_usd가 큰 값을 반환하여 cost_exceeded 가드 검증 가능.
    """
    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    chat.temperature = None
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": in_tok, "output_tokens": out_tok}
    chat.invoke.return_value = resp
    return chat


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    content: str,
    *,
    in_tok: int = 0,
    out_tok: int = 0,
) -> None:
    monkeypatch.setattr(
        target, lambda *a, **k: _make_chat(content, in_tok=in_tok, out_tok=out_tok)
    )


def _make_tracker(tmp_path: Path) -> LLMCallTracker:
    return LLMCallTracker("test-routing", tmp_path / "traces")


def _arch_response(samples: list[dict[str, Any]]) -> str:
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


def _adv_response(inputs: list[dict[str, Any]]) -> str:
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


def _default_budget() -> dict[str, int]:
    return {"architect": 2, "coder": 4, "auditor": 2, "generator": 2}


def _build_initial(
    *,
    max_iter: int = 5,
    max_cost_usd: float = 100.0,
    budget: dict[str, int] | None = None,
) -> ProblemState:
    return {
        "target_algorithm": "A+B",
        "target_language": "python",
        "iteration_count": 0,
        "max_iter": max_iter,
        "max_cost_usd": max_cost_usd,
        "node_retry_budget": (budget or _default_budget()),  # type: ignore[typeddict-item]
        "iteration_history": [],
        "llm_calls": [],
    }


def _wire_all_chats(
    monkeypatch: pytest.MonkeyPatch,
    *,
    coder_response: str = VALID_CODER,
    in_tok: int = 0,
    out_tok: int = 0,
) -> None:
    _patch(monkeypatch, "ipe.nodes.architect.get_chat",
           _arch_response(VALID_SAMPLES), in_tok=in_tok, out_tok=out_tok)
    _patch(monkeypatch, "ipe.nodes.coder.get_chat", coder_response,
           in_tok=in_tok, out_tok=out_tok)
    _patch(monkeypatch, "ipe.nodes.auditor.get_chat", _adv_response(VALID_ADV),
           in_tok=in_tok, out_tok=out_tok)
    _patch(monkeypatch, "ipe.nodes.generator.get_chat", GEN_RESPONSE,
           in_tok=in_tok, out_tok=out_tok)


# =============================================================================
# graph.invoke 통합 — full cycle
# =============================================================================


def test_happy_path_full_cycle_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """architect+coder+auditor+generator 모두 정상 mock → graph.invoke → success."""
    _wire_all_chats(monkeypatch)

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    final = graph.invoke(_build_initial())
    assert final.get("final_status") == "success", (
        f"got {final.get('final_status')} "
        f"(failed={final.get('last_failed_node')}: {final.get('feedback_message')!r})"
    )
    assert final.get("last_failed_node") is None
    testcases = final.get("testcases") or []
    assert any(t.get("kind") == "sample" for t in testcases)
    assert any(t.get("kind") == "adversarial" for t in testcases)
    assert any(t.get("kind") == "generated" for t in testcases)


def test_coder_budget_exhausted_halt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """잘못된 코드(print(0)) 반복 → coder 라우팅 누적 → budget_exhausted halt.

    coder budget=2로 설정 → 2회 retry 후 3번째 fail에서 budget_exhausted.
    """
    _wire_all_chats(monkeypatch, coder_response=BAD_CODER)

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    budget = _default_budget()
    budget["coder"] = 2
    final = graph.invoke(_build_initial(budget=budget))

    assert final.get("final_status") == "budget_exhausted"
    assert "coder" in (final.get("feedback_message") or "")
    # iteration_history에 coder 시도가 누적되었어야 함
    history = final.get("iteration_history") or []
    coder_entries = [h for h in history if h.get("node") == "coder"]
    assert len(coder_entries) >= 2


def test_max_iter_halt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """max_iter=1 + 잘못된 코드 → 1 cycle 후 max_iterations halt."""
    _wire_all_chats(monkeypatch, coder_response=BAD_CODER)

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    final = graph.invoke(_build_initial(max_iter=1))
    assert final.get("final_status") == "max_iterations"
    assert final.get("iteration_count") == 1


def test_cost_exceeded_halt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """큰 토큰 사용 + max_cost_usd=0.01 → 첫 cycle에서 cost_exceeded.

    Opus pricing: 10k in + 10k out → ($0.15 + $0.75) = $0.90 per call.
    architect 1 call만 호출되어도 max=$0.01 초과 — decision에서 즉시 halt.
    """
    _wire_all_chats(monkeypatch, coder_response=BAD_CODER, in_tok=10000, out_tok=10000)

    tracker = _make_tracker(tmp_path)
    runner = RlimitRunner()
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    final = graph.invoke(_build_initial(max_cost_usd=0.01))
    assert final.get("final_status") == "cost_exceeded"
    feedback = final.get("feedback_message") or ""
    assert "cost guard" in feedback
