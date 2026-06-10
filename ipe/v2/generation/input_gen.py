"""결정론적 입력 생성 엔진 — GeneratorContract + io_schema → 입력 문자열 (M4 step3).

LLM(step2)이 설계한 ``GeneratorContract``(scale_families + edge_cases)와 frozen
``io_schema``(필드 타입/범위)를 받아, **seeded RNG 로 결정론** 입력을 만든다. 같은
(contract, io_schema, seed) 면 항상 같은 입력 → 재현가능 채점셋.

직렬화 규약 (canonical, 필드별 줄 단위):
- ``int`` / ``bool`` / ``float`` : 한 줄 스칼라 (bool=1/0, float=소수4자리).
- ``string`` : 한 줄 영소문자 (길이=size, 최소 1 — 빈 입력 금지).
- ``int_array`` : ``N`` 줄 + ``N`` 개 공백구분 정수 줄 (N=0 면 ``0`` 만).
- ``int_matrix`` : ``R C`` 줄 + R 개의 (C 개 정수) 줄.
- 여러 필드는 io_schema 순서로 줄 join.

규약은 step4 골든 파서와 맞아야 한다(현재 결합 = known item, step4/5 에서 검증).
graph/grid(``weighted_edges``/``tree_edges``/``grid``)는 cross-field(V/E 조율) 결합이라
**step3b 로 이연** — ``NotImplementedError``.

tier 적용: ScaleFamily.field_bounds(이름=필드명)는 스칼라의 **값**, sized 타입의
**크기**를 그 tier 로 좁힌다. array/matrix 의 원소 값은 io_schema.value_range.
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

# graph/grid 는 V/E cross-field 결합 → step3b 로 이연
_DEFERRED_TYPES = frozenset({"weighted_edges", "tree_edges", "grid"})

_Bias = Literal["random", "empty", "min", "max"]


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
    if t in _DEFERRED_TYPES:
        msg = f"io_type '{t}' 는 M4 step3b(graph/grid)에서 지원 — 현재 미지원"
        raise NotImplementedError(msg)
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
    if t == "int_matrix":
        return _serialize_int_matrix(field, tier_bound, rng, bias=bias)
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
    if any(k in low for k in ("empty", "zero", "null")):
        return "empty"
    if any(k in low for k in ("max", "large", "stress", "big", "full", "huge", "upper")):
        return "max"
    # single/one/min/small/lower/tiny + 미인식 → 하한 경계
    return "min"
