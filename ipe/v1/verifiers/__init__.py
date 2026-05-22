"""IPE v1 symbolic verifiers — algorithm-specific 결정론적 검증 (D안 H2).

각 verifier 는 한 algorithm 의 수학적 invariants 를 코드 실행 결과로 검증.
LLM judgment 와 독립된 anchor — fixture 가 통과하면 정답 보장.

Phase 1 = Dijkstra 만. Phase 2 에서 LIS, SegmentTree 등 추가.
"""

from __future__ import annotations

from .base import SymbolicVerifier, get_verifier, register_verifier
from .dijkstra import DijkstraVerifier

# Phase 1: 시작 시 DijkstraVerifier 자동 등록.
register_verifier(DijkstraVerifier())

__all__ = [
    "DijkstraVerifier",
    "SymbolicVerifier",
    "get_verifier",
    "register_verifier",
]
