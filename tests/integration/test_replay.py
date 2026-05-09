"""Replay 통합 테스트 (P8.5).

스펙: ARCHITECTURE.md §3.4, IMPLEMENTATION_ROADMAP §1 P8.5
범위: ``ReplayTracker``가 LLM 호출 0회로 cached trace를 재현.

시나리오:
1. record + replay — 정상 run으로 traces 저장 → ReplayTracker로 재실행 →
   chat.invoke 호출 0건 + final_status='success' + 같은 testcases 산출
2. replay miss — traces가 비어있으면 ``RuntimeError("replay miss")``
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
from ipe.observability import LLMCallTracker, ReplayTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.state import ProblemState

# =============================================================================
# 공통 helpers
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


def _make_chat_forbid_invoke() -> MagicMock:
    """LLM이 호출되면 즉시 fail — replay 검증용."""
    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    chat.temperature = None
    chat.invoke.side_effect = AssertionError(
        "chat.invoke must NOT be called during replay"
    )
    return chat


def _patch_forbid(monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    monkeypatch.setattr(target, lambda *a, **k: _make_chat_forbid_invoke())


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


def _wire_all_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, "ipe.nodes.architect.get_chat", _arch_response(VALID_SAMPLES))
    _patch(monkeypatch, "ipe.nodes.coder.get_chat", VALID_CODER)
    _patch(monkeypatch, "ipe.nodes.auditor.get_chat", _adv_response(VALID_ADV))
    _patch(monkeypatch, "ipe.nodes.generator.get_chat", GEN_RESPONSE)


def _wire_all_forbid_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """모든 노드의 chat.invoke를 금지 — ReplayTracker가 우회해야 PASS."""
    for node in ("architect", "coder", "auditor", "generator"):
        _patch_forbid(monkeypatch, f"ipe.nodes.{node}.get_chat")


# =============================================================================
# 시나리오 1 — record + replay
# =============================================================================


def test_replay_zero_llm_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """정상 run → traces 저장. 같은 traces로 ReplayTracker 사용 → chat.invoke 0회.

    Definition of Done: ``--replay <run_id>`` → LLM 호출 0회 발생.
    """
    traces_dir = tmp_path / "traces"
    db_record = tmp_path / "checkpoint_record.db"
    db_replay = tmp_path / "checkpoint_replay.db"
    runner = RlimitRunner()

    # ── 1단계: record (정상 LLM mock + LLMCallTracker)
    _wire_all_normal(monkeypatch)

    with SqliteSaver.from_conn_string(str(db_record)) as saver:
        tracker = LLMCallTracker("record-run", traces_dir)
        graph = build_graph(
            tracker=tracker, runner=runner,
            workdir_root=tmp_path / "wd_rec", checkpointer=saver,
        )
        config: dict[str, Any] = {
            "configurable": {"thread_id": "record"}, "recursion_limit": 60,
        }
        record_final = graph.invoke(_initial_state(), config=config)

    assert record_final.get("final_status") == "success"
    trace_files = list(traces_dir.glob("*.json"))
    assert len(trace_files) >= 4, f"expected ≥4 traces, got {len(trace_files)}"

    # ── 2단계: replay (chat.invoke 호출 시 AssertionError + ReplayTracker)
    _wire_all_forbid_invoke(monkeypatch)

    with SqliteSaver.from_conn_string(str(db_replay)) as saver:
        replay_tracker = ReplayTracker("replay-run", traces_dir)
        graph = build_graph(
            tracker=replay_tracker, runner=runner,
            workdir_root=tmp_path / "wd_rep", checkpointer=saver,
        )
        config_replay: dict[str, Any] = {
            "configurable": {"thread_id": "replay"}, "recursion_limit": 60,
        }
        replay_final = graph.invoke(_initial_state(), config=config_replay)

    # chat.invoke가 한 번도 호출되지 않은 상태여야 success까지 도달
    assert replay_final.get("final_status") == "success"
    # 기록된 LLM call 수가 record run과 일치해야 함
    assert len(replay_final.get("llm_calls") or []) == len(trace_files)


# =============================================================================
# 시나리오 2 — replay miss
# =============================================================================


def test_replay_miss_raises_when_no_traces(tmp_path: Path) -> None:
    """traces_dir이 비어있으면 ReplayTracker.invoke가 첫 호출에서 즉시 raise."""
    empty_traces = tmp_path / "empty_traces"
    empty_traces.mkdir()
    tracker = ReplayTracker("empty-run", empty_traces)

    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    state_calls: list[Any] = []

    with pytest.raises(RuntimeError, match="replay miss"):
        tracker.invoke(chat, [], node="architect", state_calls=state_calls)
