"""real-LLM e2e — full mode 병렬 synthesis (Phase 3 M2 step4 검증).

Marked ``@pytest.mark.e2e`` — CI 의 ``pytest -m "not e2e and not slow"`` 는 skip.
ANTHROPIC_API_KEY env 필요. 1 run ≈ architect + designer + golden×2 + brute
(+ reconcile/executor sandbox 실행) = approx 5 LLM calls, cost approx $1-2.

Gate 의도(기존 canonical e2e 와 동일): **full mode 그래프가 실 LLM + sandbox 통합
경로에서 crash 없이 end 까지 도달** + valid full-mode final_status 종료. quality
측정 아님 — fan-out/fan-in/bridge/executor 배선이 실제로 동작하는지의 pipeline 검증.

Run::

    set -a; source .env; set +a
    .venv/bin/pytest -m e2e tests/v1/test_e2e_full_mode_real_llm.py -v
"""

from __future__ import annotations

import os

import pytest

from ipe.v1.graph import build_graph
from ipe.v1.main_v1 import _normalize_final_state
from ipe.v1.nodes import AnthropicCoderLLM
from ipe.v1.schema import TargetAlgorithm
from ipe.v1.state import initial_state

VALID_FULL_FINAL_STATUSES = {
    "success",
    "fail_synthesis_rejected",
    "fail_verification",
}


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY missing — real LLM e2e skipped",
)
def test_full_mode_single_run_real_llm() -> None:
    """1 run Dijkstra, full mode, distinct-model golden×2(opus/sonnet) + brute.

    검증:
    - ``build_graph(mode='full')`` + invoke 가 LangGraph fan-out/fan-in +
      Anthropic + sandbox 통합 path 에서 crash 없이 동작.
    - ``reconciliation`` 이 항상 채워짐 (fan-in 도달).
    - ``candidates`` 가 정확히 3 (golden×2 + brute, dedup reducer 멱등 — origin/
      fanout_index 가 달라 코드 동일해도 distinct).
    - ``final_status`` 가 full-mode valid enum 으로 종료.

    quality (success rate 등) 검증은 별도 N=3 측정 (follow-up).
    """
    graph = build_graph(
        mode="full",
        golden_llms=[
            AnthropicCoderLLM("claude-opus-4-7"),
            AnthropicCoderLLM("claude-sonnet-4-6"),
        ],
        brute_llm=AnthropicCoderLLM("claude-opus-4-7"),
        golden_origins=["opus", "sonnet"],
        brute_origin="brute",
    )
    initial = initial_state("m2-step4-e2e", TargetAlgorithm.DIJKSTRA)
    raw = graph.invoke(initial)
    final = _normalize_final_state(raw)

    assert final.final_status in VALID_FULL_FINAL_STATUSES
    assert final.reconciliation is not None  # fan-in 도달
    assert len(final.candidates) == 3  # fan-out 누적, 중복 없음
    if final.final_status == "success":
        assert final.reconciliation.all_agree is True
        assert final.attempt is not None
        assert final.verification is not None
        assert final.verification.overall_pass is True
