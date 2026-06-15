"""결정적 canonical stdin 파서 렌더 — io_schema → 파이썬 파싱 preamble (#2 병목).

``input_gen`` 의 직렬화 규약(같은 모듈 docstring)의 **역함수**를 코드로 렌더한다.
spec_bridge 가 이 preamble 을 ``ProblemSpec.input_parser_code`` 로 freeze 하면,
synthesis 의 모든 golden/brute 코더가 **같은·정확한 파서**를 전문(preamble)으로 받아
알고리즘만 작성한다.

왜 코드 주입인가 (prose 규율의 한계):
19-algo 배치 진단상 배열/값 시드 출하의 1위 병목은 코더가 stdin 파서를 LLM 으로 직접
작성해 생기는 **파서 분산**이었다 — ① graph(weighted_edges) 뒤 후행 스칼라(s/t/cap)를
간선으로 오소비해 IndexError, ② 중복 카운트 io_schema(독립 N + 자기기술 배열)를 코더마다
다르게 파싱. coder.py 의 prose ``_PARSE_DISCIPLINE``(#141)과 formalizer 의 중복카운트
금지(#148)는 이미 있으나 약한 모델(sonnet)이 신뢰성 있게 따르지 못한다. 파서를 **코드로
파생**하면 분산 자체가 사라진다(모든 코더 동일 토큰 소비 → reconcile 합의).

견고성: stdin 전체를 **평탄 토큰 리스트**로 읽어 io_schema 필드 순서대로 정확한 개수만
소비한다. 줄 경계 변형(공백/개행)에 무관. string 은 canonical 직렬화상 공백 없는 영소문자
한 줄이라 split 토큰 1개로 안전. int_array 의 N=0(원소 줄 없음)·tree_edges 의 V-1 간선·
weighted_edges 의 E 트리플 모두 헤더 개수로 정확히 소비 → 리스트 끝 초과(IndexError) 차단.

바인딩 규약 (코더가 쓰는 변수 — coder 프롬프트가 함께 안내):
- int / bool        : ``name`` = int
- float             : ``name`` = float
- string            : ``name`` = str
- int_array         : ``name`` = list[int]            (길이는 헤더에서, 미사용 카운트는 무시)
- int_matrix / grid : ``name`` = list[list[int]]      (R×C)
- weighted_edges    : ``name`` = (V, E, list[(u, v, w)])   (1-indexed)
- tree_edges        : ``name`` = (V, list[(u, v)])  또는 value_range 시 (V, list[(u, v, w)])
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ipe.v1.schema import IOFieldSpec, IOSchema

# preamble 공용 헬퍼 — flat 토큰 리더. weighted/tree 의 trailing 스칼라 오소비를
# 구조적으로 차단(헤더 개수만큼만 소비). value 미사용 카운트도 토큰만 먹고 버린다.
_HELPER = """\
import sys as _sys
_tok = _sys.stdin.buffer.read().split()
_ptr = 0
def _rd_int():
    global _ptr
    v = int(_tok[_ptr]); _ptr += 1; return v
def _rd_str():
    global _ptr
    v = _tok[_ptr].decode(); _ptr += 1; return v
def _rd_ints(_n):
    global _ptr
    v = [int(x) for x in _tok[_ptr:_ptr + _n]]; _ptr += _n; return v"""


def _render_field_parse(field: IOFieldSpec) -> str:
    """io_schema 한 필드 → 그 필드를 변수에 바인딩하는 파싱 코드 줄(들)."""
    name = field.name
    t = field.type
    if t in ("int", "bool"):
        return f"{name} = _rd_int()"
    if t == "float":
        return f"{name} = float(_rd_str())"
    if t == "string":
        return f"{name} = _rd_str()"
    if t == "int_array":
        # 첫 토큰 = 원소 개수 N, 이어서 N 개. N=0 이면 빈 리스트.
        return f"_n = _rd_int()\n{name} = _rd_ints(_n)"
    if t in ("int_matrix", "grid"):
        return (
            "_r = _rd_int(); _c = _rd_int()\n"
            f"{name} = [_rd_ints(_c) for _ in range(_r)]"
        )
    if t == "weighted_edges":
        # 'V E' 헤더 + E 줄 'u v w' (1-indexed). 후행 스칼라 오소비 차단.
        return (
            "_v = _rd_int(); _e = _rd_int()\n"
            f"{name} = (_v, _e, [(_rd_int(), _rd_int(), _rd_int()) "
            "for _ in range(_e)])"
        )
    if t == "tree_edges":
        # 'V' 헤더 + (V-1) 줄. value_range 있으면 'u v w', 없으면 'u v'.
        if field.value_range is not None:
            edge = "(_rd_int(), _rd_int(), _rd_int())"
        else:
            edge = "(_rd_int(), _rd_int())"
        return (
            "_v = _rd_int()\n"
            f"{name} = (_v, [{edge} for _ in range(_v - 1)])"
        )
    msg = f"io_type '{t}' 파서 렌더 미지원"
    raise NotImplementedError(msg)


def render_input_parser(io_schema: IOSchema) -> str:
    """io_schema → stdin 파싱 preamble (파이썬 코드 문자열).

    ``input_gen._serialize_field`` 직렬화의 역함수 — 두 함수는 같은 canonical 규약을
    본다(드리프트=출하실패의 원인이라 round-trip 테스트로 가드). 코더는 이 preamble 을
    그대로 코드 앞에 두고, 바인딩된 필드 변수로 알고리즘을 작성한다.
    """
    parts = [_HELPER]
    for field in io_schema.inputs:
        parts.append(f"# {field.name}: {field.type}")
        parts.append(_render_field_parse(field))
    return "\n".join(parts)
