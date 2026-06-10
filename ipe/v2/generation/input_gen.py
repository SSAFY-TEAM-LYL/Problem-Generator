"""결정론적 입력 생성 엔진 — GeneratorContract + io_schema → 입력 문자열 (M4 step3).

LLM(step2)이 설계한 ``GeneratorContract``(scale_families + edge_cases)와 frozen
``io_schema``(필드 타입/범위)를 받아, **seeded RNG 로 결정론** 입력을 만든다. 같은
(contract, io_schema, seed) 면 항상 같은 입력 → 재현가능 채점셋.

직렬화 규약 (canonical, 필드별 줄 단위):
- ``int`` / ``bool`` / ``float`` : 한 줄 스칼라 (bool=1/0, float=소수4자리).
- ``string`` : 한 줄 영소문자 (길이=size, 최소 1 — 빈 입력 금지).
- ``int_array`` : ``N`` 줄 + ``N`` 개 공백구분 정수 줄 (N=0 면 ``0`` 만).
- ``int_matrix`` : ``R C`` 줄 + R 개의 (C 개 정수) 줄.
- ``weighted_edges`` (step3b) : ``V E`` 줄 + E 줄 ``u v w`` (**1-indexed**, self-loop
  없음, w=value_range). 랜덤 부착 backbone 으로 **연결 보장** + extra 간선(다중간선
  허용). bias: min=트리 밀도(E=V-1) / max=조밀 / empty=``1 0`` / disconnected=정확히
  두 컴포넌트(backbone ×2, E=V-2).
- ``tree_edges`` (step3b) : ``V`` 줄 + (V-1) 줄 ``u v`` — value_range 있으면
  ``u v w``. 랜덤 부착 트리(연결+무사이클 보장). empty=``1``.
- ``grid`` (step3b) : ``int_matrix`` 와 동일 규약 (의미 구분은 blueprint 몫).
- 여러 필드는 io_schema 순서로 줄 join.

graph 필드는 **self-contained** (V/E 헤더 포함) — V:int 필드를 따로 두는 분리 모델링
은 중복/모순을 낳으므로 formalizer prompt 가 단일 graph 필드로 유도한다. 정점 참조
스칼라(s/t 등)의 value_range ↔ V 결합은 formalizer 책임(size 하한 이내). 규약↔골든
파서 정합은 assembled 비율 anchor 로 실측(known item).

tier 적용: ScaleFamily.field_bounds(이름=필드명)는 스칼라의 **값**, sized 타입의
**크기**(graph 는 정점 수 V)를 그 tier 로 좁힌다. 원소/가중치 값은 io_schema 의
value_range.
"""

from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING, Literal

from ipe.v1.schema import GeneratedTestCase

if TYPE_CHECKING:
    from ipe.v1.schema import (
        ConstraintRange,
        GeneratorContract,
        IOFieldSpec,
        IOSchema,
    )

# 범위 미지정 시 기본값
_DEFAULT_SIZE = (1, 10)
_DEFAULT_VALUE = (0, 100)
_STRING_MIN_LEN = 1  # 빈 문자열 금지 (GeneratedTestCase.input_text min_length=1 보존)
_ALPHABET = "abcdefghijklmnopqrstuvwxyz"

# "disconnected" 는 graph 타입 전용 의미(두 컴포넌트) — 비-graph 필드에선 random 취급
_Bias = Literal["random", "empty", "min", "max", "disconnected"]


def seed_from_run_id(run_id: str) -> int:
    """run_id → 안정적 seed (내장 ``hash()`` 는 PYTHONHASHSEED 의존이라 비결정)."""
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def generate_inputs(
    contract: GeneratorContract,
    io_schema: IOSchema,
    *,
    seed: int,
) -> tuple[GeneratedTestCase, ...]:
    """contract + io_schema → 결정론 입력들 (expected=None pending).

    scale_families 각 tier 에서 ``case_count`` 개 + edge_cases 각 1 개. category 는
    출처(tier/edge name). 같은 seed → 같은 결과.
    """
    rng = random.Random(seed)
    cases: list[GeneratedTestCase] = []
    for family in contract.scale_families:
        tier_bounds = {cr.name: cr for cr in family.field_bounds}
        for _ in range(family.case_count):
            text = _serialize_inputs(io_schema, tier_bounds, rng, bias="random")
            cases.append(GeneratedTestCase(input_text=text, category=family.name))
    for edge in contract.edge_cases:
        text = _serialize_inputs(io_schema, {}, rng, bias=_edge_bias(edge.name))
        cases.append(GeneratedTestCase(input_text=text, category=edge.name))
    return tuple(cases)


def _serialize_inputs(
    io_schema: IOSchema,
    tier_bounds: dict[str, ConstraintRange],
    rng: random.Random,
    *,
    bias: _Bias,
) -> str:
    parts = [
        _serialize_field(f, tier_bounds.get(f.name), rng, bias=bias)
        for f in io_schema.inputs
    ]
    return "\n".join(parts)


def _serialize_field(
    field: IOFieldSpec,
    tier_bound: ConstraintRange | None,
    rng: random.Random,
    *,
    bias: _Bias,
) -> str:
    t = field.type
    if t == "int":
        return str(_pick_value(_value_bounds(field, tier_bound), bias, rng))
    if t == "bool":
        return "1" if _bool_value(bias, rng) else "0"
    if t == "float":
        lo, hi = _value_bounds(field, tier_bound)
        return f"{_pick_float(lo, hi, bias, rng):.4f}"
    if t == "string":
        n = max(_pick_size(_size_bounds(field, tier_bound), bias, rng), _STRING_MIN_LEN)
        return "".join(rng.choice(_ALPHABET) for _ in range(n))
    if t == "int_array":
        return _serialize_int_array(field, tier_bound, rng, bias=bias)
    if t in ("int_matrix", "grid"):  # grid = int_matrix 와 동일 canonical 규약
        return _serialize_int_matrix(field, tier_bound, rng, bias=bias)
    if t == "weighted_edges":
        return _serialize_weighted_edges(field, tier_bound, rng, bias=bias)
    if t == "tree_edges":
        return _serialize_tree_edges(field, tier_bound, rng, bias=bias)
    msg = f"io_type '{t}' 미지원"
    raise NotImplementedError(msg)


def _serialize_int_array(
    field: IOFieldSpec,
    tier_bound: ConstraintRange | None,
    rng: random.Random,
    *,
    bias: _Bias,
) -> str:
    n = _pick_size(_size_bounds(field, tier_bound), bias, rng)
    if n <= 0:
        return "0"
    lo, hi = _element_bounds(field)
    vals = " ".join(str(rng.randint(lo, hi)) for _ in range(n))
    return f"{n}\n{vals}"


def _serialize_int_matrix(
    field: IOFieldSpec,
    tier_bound: ConstraintRange | None,
    rng: random.Random,
    *,
    bias: _Bias,
) -> str:
    size = _size_bounds(field, tier_bound)
    r = _pick_size(size, bias, rng)
    c = _pick_size(size, bias, rng)
    if r <= 0 or c <= 0:
        return f"{max(r, 0)} {max(c, 0)}"
    lo, hi = _element_bounds(field)
    rows = "\n".join(
        " ".join(str(rng.randint(lo, hi)) for _ in range(c)) for _ in range(r)
    )
    return f"{r} {c}\n{rows}"


# ---------- graph serialization (step3b) ----------


def _backbone(start: int, end: int, rng: random.Random) -> list[tuple[int, int]]:
    """정점 ``start..end`` 를 잇는 랜덤 부착 트리 간선 — 연결+무사이클 보장.

    각 정점 i 를 이미 존재하는 정점(start..i-1) 중 하나에 붙인다 (self-loop 불가능).
    """
    return [(rng.randint(start, i - 1), i) for i in range(start + 1, end + 1)]


def _graph_vertex_count(
    field: IOFieldSpec,
    tier_bound: ConstraintRange | None,
    rng: random.Random,
    bias: _Bias,
) -> int:
    """graph 정점 수 V — size 범위에서. disconnected 는 크기 자체는 random."""
    size_bias: _Bias = "random" if bias == "disconnected" else bias
    return max(_pick_size(_size_bounds(field, tier_bound), size_bias, rng), 1)


def _serialize_weighted_edges(
    field: IOFieldSpec,
    tier_bound: ConstraintRange | None,
    rng: random.Random,
    *,
    bias: _Bias,
) -> str:
    """``V E`` + E 줄 ``u v w`` (1-indexed). backbone 연결 + bias 별 밀도/구조."""
    if bias == "empty":
        return "1 0"  # 단일 정점, 간선 0 (퇴화 최소 그래프)
    v = _graph_vertex_count(field, tier_bound, rng, bias)
    if bias == "disconnected":
        v = max(v, 2)  # 두 컴포넌트가 가능한 최소
        half = (v + 1) // 2
        edges = _backbone(1, half, rng) + _backbone(half + 1, v, rng)
    else:
        edges = _backbone(1, v, rng)
        extra = 0 if bias == "min" else (v if bias == "max" else rng.randint(0, v))
        if v >= 2:
            for _ in range(extra):
                u = rng.randint(1, v)
                t = rng.randint(1, v - 1)
                if t >= u:  # self-loop 회피 (다중간선은 허용)
                    t += 1
                edges.append((u, t))
    lo, hi = _element_bounds(field)  # value_range = 가중치
    lines = [f"{u} {t} {rng.randint(lo, hi)}" for u, t in edges]
    return "\n".join([f"{v} {len(edges)}", *lines])


def _serialize_tree_edges(
    field: IOFieldSpec,
    tier_bound: ConstraintRange | None,
    rng: random.Random,
    *,
    bias: _Bias,
) -> str:
    """``V`` + (V-1) 줄 ``u v`` (value_range 있으면 ``u v w``). 랜덤 부착 트리.

    트리는 정의상 연결 — disconnected bias 는 크기 random 으로만 작용.
    """
    if bias == "empty":
        return "1"  # 단일 정점 트리
    v = _graph_vertex_count(field, tier_bound, rng, bias)
    edges = _backbone(1, v, rng)
    if field.value_range is not None:
        lo, hi = _element_bounds(field)
        lines = [f"{u} {t} {rng.randint(lo, hi)}" for u, t in edges]
    else:
        lines = [f"{u} {t}" for u, t in edges]
    return "\n".join([str(v), *lines])


# ---------- bounds resolution ----------


def _range_or(cr: ConstraintRange | None, default: tuple[int, int]) -> tuple[int, int]:
    return (cr.min_value, cr.max_value) if cr is not None else default


def _value_bounds(
    field: IOFieldSpec, tier_bound: ConstraintRange | None
) -> tuple[int, int]:
    """스칼라 값 범위 — tier 가 우선 좁힘, 없으면 io_schema.value_range."""
    cr = tier_bound if tier_bound is not None else field.value_range
    return _range_or(cr, _DEFAULT_VALUE)


def _size_bounds(
    field: IOFieldSpec, tier_bound: ConstraintRange | None
) -> tuple[int, int]:
    """sized 타입 크기 범위 — tier 가 우선 좁힘, 없으면 io_schema.size_range."""
    cr = tier_bound if tier_bound is not None else field.size_range
    return _range_or(cr, _DEFAULT_SIZE)


def _element_bounds(field: IOFieldSpec) -> tuple[int, int]:
    """array/matrix 원소 값 범위 — io_schema.value_range (tier 무관)."""
    return _range_or(field.value_range, _DEFAULT_VALUE)


# ---------- bias picks ----------


def _pick_value(bounds: tuple[int, int], bias: _Bias, rng: random.Random) -> int:
    lo, hi = bounds
    if bias in ("min", "empty"):
        return lo
    if bias == "max":
        return hi
    return rng.randint(lo, hi)


def _pick_float(lo: int, hi: int, bias: _Bias, rng: random.Random) -> float:
    if bias in ("min", "empty"):
        return float(lo)
    if bias == "max":
        return float(hi)
    return rng.uniform(lo, hi)


def _pick_size(bounds: tuple[int, int], bias: _Bias, rng: random.Random) -> int:
    lo, hi = bounds
    if bias == "empty":
        return 0
    if bias == "min":
        return lo
    if bias == "max":
        return hi
    return rng.randint(lo, hi)


def _bool_value(bias: _Bias, rng: random.Random) -> bool:
    if bias in ("min", "empty"):
        return False
    if bias == "max":
        return True
    return rng.randint(0, 1) == 1


def _edge_bias(name: str) -> _Bias:
    """edge 케이스 이름 → boundary 전략 (generic keyword 해석)."""
    low = name.lower()
    # graph 전용 의미가 가장 구체적 — 먼저 매칭 ('disconnected_large' 등 복합어 보호)
    if any(k in low for k in ("disconnect", "unreachable", "isolated")):
        return "disconnected"
    if any(k in low for k in ("empty", "zero", "null")):
        return "empty"
    if any(k in low for k in ("max", "large", "stress", "big", "full", "huge", "upper")):
        return "max"
    # single/one/min/small/lower/tiny + 미인식 → 하한 경계
    return "min"
