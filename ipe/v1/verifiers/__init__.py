"""IPE v1 symbolic verifiers — algorithm-specific 결정론적 검증 (D안 H2).

각 verifier 는 한 algorithm 의 수학적 invariants 를 코드 실행 결과로 검증.
LLM judgment 와 독립된 anchor — fixture 가 통과하면 정답 보장.

Phase 1 = Dijkstra 만. Phase 2 에서 LIS, SegmentTree 등 추가.
"""

from __future__ import annotations

from .base import SymbolicVerifier, get_verifier, register_verifier
from .bellman_ford import BellmanFordVerifier
from .bfs import BFSVerifier
from .binary_search import BinarySearchVerifier
from .dijkstra import DijkstraVerifier
from .knapsack import KnapsackVerifier
from .lis import LISVerifier
from .maxflow import MaxFlowVerifier
from .segtree import SegmentTreeVerifier
from .sieve import SieveVerifier
from .sort import SortVerifier
from .stringmatch import StringMatchVerifier
from .toposort import TopologicalSortVerifier
from .twosum import TwoSumVerifier
from .union_find import UnionFindVerifier

# Phase 1: DijkstraVerifier 자동 등록.
# Phase 2a (PR-B1): LISVerifier 자동 등록.
# Phase 2a (PR-B2): SegmentTreeVerifier 자동 등록.
# Phase 2a (PR-B3): TwoSumVerifier 자동 등록.
# Phase 2a (PR-B4): BFSVerifier 자동 등록 (baseline 5 완성).
# Phase 2b (PR-C1): BinarySearchVerifier 자동 등록.
# Phase 2b (PR-C2): UnionFindVerifier 자동 등록.
# Phase 2b (PR-C3): TopologicalSortVerifier 자동 등록.
# Phase 2b (PR-C4): KnapsackVerifier 자동 등록.
# Phase 2b (PR-C5): SortVerifier 자동 등록.
# Phase 2b (PR-C6): StringMatchVerifier 자동 등록.
# Phase 2b (PR-C7): MaxFlowVerifier 자동 등록.
# Phase 2b (PR-C8): SieveVerifier 자동 등록 — Phase 2b 마무리.
# Phase 2c (PR-D1): BellmanFordVerifier 자동 등록 — Graph family 확장 시작.
register_verifier(DijkstraVerifier())
register_verifier(LISVerifier())
register_verifier(SegmentTreeVerifier())
register_verifier(TwoSumVerifier())
register_verifier(BFSVerifier())
register_verifier(BinarySearchVerifier())
register_verifier(UnionFindVerifier())
register_verifier(TopologicalSortVerifier())
register_verifier(KnapsackVerifier())
register_verifier(SortVerifier())
register_verifier(StringMatchVerifier())
register_verifier(MaxFlowVerifier())
register_verifier(SieveVerifier())
register_verifier(BellmanFordVerifier())

__all__ = [
    "BFSVerifier",
    "BellmanFordVerifier",
    "BinarySearchVerifier",
    "DijkstraVerifier",
    "KnapsackVerifier",
    "LISVerifier",
    "MaxFlowVerifier",
    "SegmentTreeVerifier",
    "SieveVerifier",
    "SortVerifier",
    "StringMatchVerifier",
    "SymbolicVerifier",
    "TopologicalSortVerifier",
    "TwoSumVerifier",
    "UnionFindVerifier",
    "get_verifier",
    "register_verifier",
]
