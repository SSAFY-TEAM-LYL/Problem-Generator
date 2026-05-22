"""real-LLM e2e test — manual trigger (D안 PR-A4).

Marked ``@pytest.mark.e2e`` — CI 의 ``pytest -m "not e2e and not slow"`` 는
skip. ANTHROPIC_API_KEY env 필요. 1 run = approx 1~3 LLM calls (architect +
designer + coder + executor; fix loop 면 추가 coder calls). cost approx $0.3-1.

Gate 의도: PR-A4 단계는 **graph 가 crash 없이 end 까지 도달** 만 확인 (quality
측정은 PR-A5 의 N=3 측정). final_status 가 4 종 중 어느 하나든 통과.

Run::

    ANTHROPIC_API_KEY=sk-... .venv/bin/pytest -m e2e tests/v1/test_e2e_real_llm.py -v
"""

from __future__ import annotations

import os

import pytest

from ipe.v1.graph import build_graph
from ipe.v1.main_v1 import _normalize_final_state
from ipe.v1.schema import TargetAlgorithm
from ipe.v1.state import initial_state

VALID_FINAL_STATUSES = {
    "success",
    "fail_budget_exhausted",
    "fail_oscillation",
    "fail_schema_violation",
}


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY missing — real LLM e2e skipped",
)
def test_dijkstra_single_run_real_llm() -> None:
    """1 run Dijkstra, real LLM, default sandbox tier.

    Phase 1 의 PR-A4 e2e 목적:
    - graph build + invoke 가 LangGraph + Anthropic + sandbox 통합 path 에서
      crash 없이 동작.
    - V1State final_status 가 4 enum 중 하나로 종료.

    Quality (success rate, samples_engaged 비율 등) 검증은 PR-A5 의 N=3 측정.
    """
    graph = build_graph()
    initial = initial_state(
        "pr-a4-e2e", TargetAlgorithm.DIJKSTRA, max_iterations=4
    )
    raw = graph.invoke(initial)
    final = _normalize_final_state(raw)

    assert final.final_status in VALID_FINAL_STATUSES
    assert final.iteration >= 1
    if final.final_status == "success":
        assert final.spec is not None
        assert final.design is not None
        assert final.attempt is not None
        assert final.verification is not None
        assert final.verification.overall_pass is True
