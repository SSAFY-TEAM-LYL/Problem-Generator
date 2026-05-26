"""IPE v1 symbolic verifiers — algorithm-specific 결정론적 검증 (D안 H2).

각 verifier 는 한 algorithm 의 수학적 invariants 를 코드 실행 결과로 검증.
LLM judgment 와 독립된 anchor — fixture 가 통과하면 정답 보장.

Phase 1 = Dijkstra 만. Phase 2 에서 LIS, SegmentTree 등 추가.
"""

from __future__ import annotations

from .base import SymbolicVerifier, get_verifier, register_verifier
from .dijkstra import DijkstraVerifier
from .lis import LISVerifier
from .segtree import SegmentTreeVerifier
from .twosum import TwoSumVerifier

# Phase 1: DijkstraVerifier 자동 등록.
# Phase 2a (PR-B1): LISVerifier 자동 등록.
# Phase 2a (PR-B2): SegmentTreeVerifier 자동 등록.
# Phase 2a (PR-B3): TwoSumVerifier 자동 등록.
register_verifier(DijkstraVerifier())
register_verifier(LISVerifier())
register_verifier(SegmentTreeVerifier())
register_verifier(TwoSumVerifier())

__all__ = [
    "DijkstraVerifier",
    "LISVerifier",
    "SegmentTreeVerifier",
    "SymbolicVerifier",
    "TwoSumVerifier",
    "get_verifier",
    "register_verifier",
]
