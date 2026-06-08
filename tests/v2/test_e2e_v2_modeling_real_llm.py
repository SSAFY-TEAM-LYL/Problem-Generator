"""real-LLM e2e — v2 은닉 모델링 그래프 (Phase 3 M3 검증).

Marked ``@pytest.mark.e2e`` — CI 의 ``pytest -m "not e2e"`` 는 skip.
ANTHROPIC_API_KEY env 필요. 1 run ≈ strategist + formalizer + narrative +
faithfulness = approx 4 LLM calls (재생성 시 +2/회), cost approx $1-2.

Gate 의도(M2 e2e 와 동일): **v2 모델링 그래프가 실 LLM 통합 경로에서 crash 없이
end 까지 도달** + valid final_status 종료 + 모델링 아티팩트(strategy/blueprint/
narrative/faithfulness) populate. quality 측정 아님 — 4-LLM 배선 + 재생성 루프가
실제로 동작하는지의 pipeline 검증.

Run::

    set -a; source .env; set +a
    .venv/bin/pytest -m e2e tests/v2/test_e2e_v2_modeling_real_llm.py -v -s
"""

from __future__ import annotations

import os

import pytest

from ipe.v1.schema import TargetAlgorithm
from ipe.v2.graph import build_v2_graph
from ipe.v2.main_v2 import _normalize_final_state
from ipe.v2.state import initial_v2_state

VALID_FINAL_STATUSES = {"success", "fail_faithfulness"}


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY missing — real LLM e2e skipped",
)
def test_v2_modeling_single_run_real_llm() -> None:
    """1 run Dijkstra seed, hidden 렌더 — 4-LLM 모델링 그래프 실통합.

    검증:
    - ``build_v2_graph()`` + invoke 가 Anthropic 4-LLM(strategist/formalizer/
      narrative/faithfulness) 통합 path 에서 crash 없이 동작.
    - 모델링 아티팩트가 모두 populate (strategy/blueprint/narrative/faithfulness).
    - blueprint.reduction_core 가 strategy 에서 carry-over (freeze 규율 실증).
    - narrative.hidden=True (은닉 렌더), domain 이 blueprint 에서 carry-over.
    - ``final_status`` 가 valid enum 으로 종료.
    """
    graph = build_v2_graph(hidden=True)
    raw = graph.invoke(
        initial_v2_state("e2e-v2-dijkstra", TargetAlgorithm.DIJKSTRA, max_iterations=4),
        config={"recursion_limit": 27},
    )
    final = _normalize_final_state(raw)

    assert final.final_status in VALID_FINAL_STATUSES, final.final_status
    assert final.strategy is not None
    assert final.blueprint is not None
    # freeze 규율: blueprint 의 알고리즘 필드는 strategy 에서 carry-over
    assert final.blueprint.reduction_core is final.strategy.reduction_core
    assert final.blueprint.domain == final.strategy.domain
    assert final.narrative is not None
    assert final.narrative.hidden is True
    assert final.narrative.domain == final.blueprint.domain
    assert final.faithfulness is not None  # round-trip 도달
