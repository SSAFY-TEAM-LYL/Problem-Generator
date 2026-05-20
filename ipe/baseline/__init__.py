"""Single-LLM baseline measurement — IPE multi-mechanism의 가치 검증용.

spec: docs/PRINCIPLES.md §3 (baseline anchor 영구화).

baseline = "1 Opus call이 problem + sample + solution + verification을 self-consistent
하게 생성". 우리 IPE pipeline (architect + designer + coder + reviewer + executor)
와 quality를 정량 비교.

진입점:
- ``run_baseline(algorithm)`` — 1 measurement
- ``BaselineResult`` — 결과 dict TypedDict
"""

from __future__ import annotations

from ipe.baseline.runner import BaselineResult, run_baseline

__all__ = ["BaselineResult", "run_baseline"]
