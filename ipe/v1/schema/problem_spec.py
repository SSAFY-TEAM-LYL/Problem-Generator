"""ProblemSpec — Architect 출력의 typed contract.

기존 (v0): ``ProblemState`` 에 prose 로 흩어져 있음 (``problem_title``,
``problem_description``, ``constraints``, ``constraints_structured``,
``sample_testcases``, ``has_special_judge``, ``special_judge_code``).

v1: 단일 immutable Pydantic 모델. 노드 간 통신을 typed structured artifacts 로
전환 (D안 H1 — information bottleneck 가설 검증).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TargetAlgorithm(StrEnum):
    """v1 graph 가 지원하는 algorithm.

    Phase 1 = Dijkstra MVR. Phase 2a = + LIS / Segment Tree / Two Sum / BFS
    (baseline 5 완성). free str 대신 enum 으로 좁혀서 symbolic verifier
    dispatch (D안 H2) 의 silent fallback 회피.
    """

    DIJKSTRA = "dijkstra"
    LIS = "lis"
    SEGTREE = "segtree"
    TWO_SUM = "two_sum"
    BFS = "bfs"
    BINARY_SEARCH = "binary_search"
    UNION_FIND = "union_find"
    TOPOSORT = "toposort"
    KNAPSACK = "knapsack"
    SORT = "sort"
    STRING_MATCH = "string_match"
    MAX_FLOW = "max_flow"
    SIEVE = "sieve"
    BELLMAN_FORD = "bellman_ford"
    FLOYD_WARSHALL = "floyd_warshall"
    KRUSKAL_MST = "kruskal_mst"
    HEAP = "heap"


class ConstraintRange(BaseModel):
    """변수의 값 범위. ``min_value``/``max_value`` 둘 다 inclusive."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., min_length=1, description="변수 이름 (예: 'N', 'V', 'E')")
    min_value: int = Field(..., description="최소값 (inclusive)")
    max_value: int = Field(..., description="최대값 (inclusive)")
    description: str = ""

    @model_validator(mode="after")
    def _check_min_le_max(self) -> ConstraintRange:
        if self.min_value > self.max_value:
            msg = (
                f"ConstraintRange '{self.name}': "
                f"min_value ({self.min_value}) > max_value ({self.max_value})"
            )
            raise ValueError(msg)
        return self


class IOContract(BaseModel):
    """문제의 입출력 형식 명세. Coder 의 parse/print 코드 anchor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_format: str = Field(..., min_length=1)
    output_format: str = Field(..., min_length=1)
    example_separator: Literal["newline", "space", "custom"] = "newline"


class SampleTestCase(BaseModel):
    """샘플 입출력. Phase A exact match anchor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_text: str
    expected_output: str
    description: str = ""


class ProblemSpec(BaseModel):
    """Architect → Designer/Coder 가 의존하는 typed problem contract.

    v1 핵심: 자연어 prose 는 ``description`` 한 필드에만. 나머지는 structured.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_algorithm: TargetAlgorithm
    title: str = Field(..., min_length=1)
    description: str = Field(
        ..., min_length=1, description="사람용 자연어 설명. LLM 은 structured 필드 우선"
    )
    constraints: list[ConstraintRange] = Field(default_factory=list)
    io_contract: IOContract
    sample_testcases: list[SampleTestCase] = Field(..., min_length=3, max_length=5)
    time_limit_ms: int = Field(default=2000, gt=0)
    memory_limit_mb: int = Field(default=256, gt=0)
