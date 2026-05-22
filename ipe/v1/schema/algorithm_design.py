"""AlgorithmDesign — Designer 출력. Coder 의 implementation 가이드 +
symbolic verifier 가 사용할 algorithm invariants.

기존 (v0): ``state["algorithm_design"]: dict[str, Any]`` (M1 RFC) — typed 아니라
구조 강제 없음.

v1 신규: ``invariants`` 필드. Dijkstra-specific symbolic verifier 가 코드 결과를
이 invariants 로 결정론적 검증 (D안 H2).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ComplexityBound(BaseModel):
    """알고리즘의 시공간 복잡도 상한."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    time_big_o: str = Field(..., min_length=1, description="예: 'O((V+E) log V)'")
    space_big_o: str = Field(..., min_length=1, description="예: 'O(V+E)'")


class Invariant(BaseModel):
    """Algorithm-specific 결정론적 성질. Symbolic verifier 가 코드 실행 결과로 검증.

    예시 (Dijkstra):
    - ``kind="non_negative_distance"``: 결과 거리 ≥ 0
    - ``kind="triangle_inequality"``: d[v] ≤ d[u] + w(u,v) for all edges (u,v)
    - ``kind="reachability_consistent"``: d[v]=∞ ⇔ v unreachable
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(
        ..., min_length=1, description="symbolic verifier 가 dispatch 하는 key"
    )
    description: str = Field(..., min_length=1)
    formal_statement: str | None = None


class EdgeCase(BaseModel):
    """알고리즘 위험 케이스. Coder prompt 에 동봉되어 implementation 가이드."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    example_input: str | None = None


class AlgorithmDesign(BaseModel):
    """Designer → Coder typed contract.

    v1 핵심: ``invariants`` 가 symbolic verifier 의 검증 대상. Coder 는 보지 않고
    Executor verifier 만 사용.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    algorithm_name: str = Field(..., min_length=1)
    complexity_target: ComplexityBound
    pseudocode: str = Field(
        ..., min_length=1, description="자연어 step 리스트 — Coder 힌트"
    )
    edge_cases: list[EdgeCase] = Field(default_factory=list)
    invariants: list[Invariant] = Field(
        default_factory=list, description="symbolic verifier 검증 대상"
    )
    data_structures: list[str] = Field(
        default_factory=list,
        description="예: ['priority_queue', 'adjacency_list']",
    )
