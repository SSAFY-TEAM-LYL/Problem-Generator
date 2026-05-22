"""IPE v1 self-measurement (D안 PR-A5).

PRINCIPLES.md 룰 1 (N≥3 measurement gate) 준수 도구. v1 graph 를 N 회 실행,
각 run 의 RunOutcome 수집 + JSONL 저장 + summary 출력.

v0 의 ``ipe.baseline`` (single-LLM baseline anchor) 와 책임 분리:
- ``ipe.baseline`` = 비교 anchor (single Opus call, multi-mechanism 없음)
- ``ipe.v1.measurement`` = v1 graph 자체의 N runs 측정 (multi-node + verifier)
"""

from __future__ import annotations

from .n3_runner import (
    RunOutcome,
    print_summary,
    run_n_measurements,
    write_jsonl,
)

__all__ = [
    "RunOutcome",
    "print_summary",
    "run_n_measurements",
    "write_jsonl",
]
