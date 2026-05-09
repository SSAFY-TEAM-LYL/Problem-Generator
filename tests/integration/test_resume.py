"""Resume 통합 테스트 (P8.5).

스펙: ARCHITECTURE.md §3.4, IMPLEMENTATION_ROADMAP §1 P8.5
범위: SqliteSaver 영속화 + 의도적 abort + ``graph.invoke(None, config)`` 재개.

시나리오:
1. checkpoint.db 자동 생성 — happy path 1회 invoke 후 db 파일 존재
2. abort + resume — 첫 invoke에서 coder가 raise → 같은 thread_id로 다시 invoke(None) →
   architect 결과는 보존된 채 coder부터 재실행 → success
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from ipe.graph import build_graph
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.state import ProblemState

# =============================================================================
# 공통 helpers (test_routing.py와 일치)
# =============================================================================


def _make_chat(content: str) -> MagicMock:
    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    chat.temperature = None
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": 0, "output_tokens": 0}
    chat.invoke.return_value = resp
    return chat


def _patch(
    monkeypatch: pytest.MonkeyPatch, target: str, content: str
) -> None:
    monkeypatch.setattr(target, lambda *a, **k: _make_chat(content))


def _patch_raises(
    monkeypatch: pytest.MonkeyPatch, target: str, exc: Exception
) -> None:
    """target.get_chat이 chat을 반환하되, chat.invoke 호출 시 exc 발생."""
    def factory(*a: Any, **k: Any) -> MagicMock:
        chat = MagicMock()
        chat.model = "claude-opus-4-7"
        chat.temperature = None
        chat.invoke.side_effect = exc
        return chat
    monkeypatch.setattr(target, factory)


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


def _initial_state() -> ProblemState:
    return {
        "target_algorithm": "A+B",
        "target_language": "python",
        "iteration_count": 0,
        "max_iter": 5,
        "max_cost_usd": 100.0,
        "node_retry_budget": _default_budget(),  # type: ignore[typeddict-item]
        "iteration_history": [],
        "llm_calls": [],
    }


def _wire_all(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, "ipe.nodes.architect.get_chat", _arch_response(VALID_SAMPLES))
    _patch(monkeypatch, "ipe.nodes.coder.get_chat", VALID_CODER)
    _patch(monkeypatch, "ipe.nodes.auditor.get_chat", _adv_response(VALID_ADV))
    _patch(monkeypatch, "ipe.nodes.generator.get_chat", GEN_RESPONSE)


# =============================================================================
# 시나리오 1 — checkpoint.db 자동 생성
# =============================================================================


def test_checkpoint_db_created_on_invoke(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SqliteSaver context로 graph.invoke 1회 → db 파일 생성됨."""
    _wire_all(monkeypatch)
    db_path = tmp_path / "checkpoint.db"
    traces_dir = tmp_path / "traces"
    runner = RlimitRunner()

    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        tracker = LLMCallTracker("run1", traces_dir)
        graph = build_graph(
            tracker=tracker, runner=runner,
            workdir_root=tmp_path / "wd", checkpointer=saver,
        )
        config: dict[str, Any] = {
            "configurable": {"thread_id": "run1"}, "recursion_limit": 60,
        }
        final = graph.invoke(_initial_state(), config=config)

    assert db_path.exists()
    assert db_path.stat().st_size > 0
    assert final.get("final_status") == "success"


# =============================================================================
# 시나리오 2 — abort + resume
# =============================================================================


def test_resume_after_coder_abort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """첫 invoke에서 coder가 raise → checkpoint.db에 architect 결과까지 저장 →
    같은 thread_id로 invoke(None) → coder부터 재실행 → success.
    """
    db_path = tmp_path / "checkpoint.db"
    traces_dir = tmp_path / "traces"
    runner = RlimitRunner()
    thread_id = "resume-thread"

    # 1단계: architect 정상, coder가 raise → 의도적 abort
    _patch(monkeypatch, "ipe.nodes.architect.get_chat", _arch_response(VALID_SAMPLES))
    _patch_raises(
        monkeypatch, "ipe.nodes.coder.get_chat",
        RuntimeError("simulated network error"),
    )

    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        tracker = LLMCallTracker("run1", traces_dir)
        graph = build_graph(
            tracker=tracker, runner=runner,
            workdir_root=tmp_path / "wd", checkpointer=saver,
        )
        config: dict[str, Any] = {
            "configurable": {"thread_id": thread_id}, "recursion_limit": 60,
        }
        with pytest.raises(RuntimeError, match="simulated network error"):
            graph.invoke(_initial_state(), config=config)

    # checkpoint.db에 architect 결과가 저장되어 있어야 함
    assert db_path.exists()

    # 2단계: 같은 thread_id로 resume — 모든 mock 정상
    _wire_all(monkeypatch)

    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        tracker = LLMCallTracker("run1", traces_dir)
        graph = build_graph(
            tracker=tracker, runner=runner,
            workdir_root=tmp_path / "wd", checkpointer=saver,
        )
        config_resume: dict[str, Any] = {
            "configurable": {"thread_id": thread_id}, "recursion_limit": 60,
        }
        final = graph.invoke(None, config=config_resume)

    assert final.get("final_status") == "success"
    # architect의 산출물이 보존되어야 함 (재호출 없이)
    assert final.get("problem_title") == "A+B"
