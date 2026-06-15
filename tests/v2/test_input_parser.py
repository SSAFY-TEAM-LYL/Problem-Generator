"""canonical stdin 파서 렌더 단위 테스트 (#2 병목 — 파서 분산 구조적 해소).

핵심 보증 = **round-trip**: ``input_gen`` 직렬화 ↔ ``render_input_parser`` 역함수가 같은
canonical 규약을 본다. 두 함수가 어긋나면(드리프트) 생성 입력에서 코더가 RTE → 출하 실패.
직접 exec 으로 생성 파서를 돌려 바인딩 변수가 직렬화 입력과 일치함을 단언한다.

추가로 **버그 재현 시나리오**를 명시 가드:
- graph(weighted_edges) + 후행 스칼라(s/t) — 후행 스칼라 오소비(IndexError) 방지.
- 중복 카운트(독립 int N + 자기기술 int_array) — 코더 균일 파싱(reconcile 합의).
"""

from __future__ import annotations

import contextlib
import io
import sys
from typing import Any

from ipe.v1.schema import (
    ConstraintRange,
    GeneratorContract,
    IOFieldSpec,
    IOSchema,
    ScaleFamily,
)
from ipe.v2.generation.input_gen import generate_inputs
from ipe.v2.generation.input_parser import render_input_parser


def _exec_parser(parser_code: str, input_text: str) -> dict[str, Any]:
    """생성 파서를 input_text 에 대해 exec → 바인딩된 모듈 namespace 반환."""

    class _FakeStdin:
        buffer = io.BytesIO(input_text.encode("utf-8"))

    ns: dict[str, Any] = {}
    orig = sys.stdin
    sys.stdin = _FakeStdin()  # type: ignore[assignment]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(parser_code, ns)  # noqa: S102 — 테스트 전용, 신뢰 입력
    finally:
        sys.stdin = orig
    return ns


def _single(field: IOFieldSpec, output_type: str = "int") -> IOSchema:
    return IOSchema(inputs=(field,), output_type=output_type, output_format="x")  # type: ignore[arg-type]


# ---------- round-trip: 각 타입 직렬화 ↔ 파서 ----------


def test_int_array_roundtrip() -> None:
    field = IOFieldSpec(
        name="arr",
        type="int_array",
        size_range=ConstraintRange(name="arr", min_value=3, max_value=8),
        value_range=ConstraintRange(name="v", min_value=-9, max_value=9),
    )
    schema = _single(field)
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=3),))
    parser = render_input_parser(schema)
    for case in generate_inputs(contract, schema, seed=7):
        ns = _exec_parser(parser, case.input_text)
        lines = case.input_text.split("\n")
        n = int(lines[0])
        expected = [int(x) for x in lines[1].split()] if n > 0 else []
        assert ns["arr"] == expected


def test_int_matrix_roundtrip() -> None:
    field = IOFieldSpec(
        name="grid",
        type="int_matrix",
        size_range=ConstraintRange(name="grid", min_value=2, max_value=4),
        value_range=ConstraintRange(name="v", min_value=0, max_value=5),
    )
    schema = _single(field)
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=3),))
    parser = render_input_parser(schema)
    for case in generate_inputs(contract, schema, seed=11):
        ns = _exec_parser(parser, case.input_text)
        lines = case.input_text.split("\n")
        r, c = (int(x) for x in lines[0].split())
        expected = [[int(x) for x in lines[1 + i].split()] for i in range(r)]
        assert ns["grid"] == expected
        assert all(len(row) == c for row in ns["grid"])


def test_weighted_edges_roundtrip() -> None:
    field = IOFieldSpec(
        name="edges",
        type="weighted_edges",
        size_range=ConstraintRange(name="V", min_value=3, max_value=6),
        value_range=ConstraintRange(name="w", min_value=1, max_value=20),
    )
    schema = _single(field)
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=3),))
    parser = render_input_parser(schema)
    for case in generate_inputs(contract, schema, seed=13):
        ns = _exec_parser(parser, case.input_text)
        v, e, triples = ns["edges"]
        lines = case.input_text.split("\n")
        hv, he = (int(x) for x in lines[0].split())
        assert (v, e) == (hv, he)
        assert len(triples) == he
        assert all(len(t) == 3 for t in triples)


def test_tree_edges_roundtrip_with_weight() -> None:
    field = IOFieldSpec(
        name="tree",
        type="tree_edges",
        size_range=ConstraintRange(name="V", min_value=2, max_value=6),
        value_range=ConstraintRange(name="w", min_value=1, max_value=9),
    )
    schema = _single(field)
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=3),))
    parser = render_input_parser(schema)
    for case in generate_inputs(contract, schema, seed=17):
        ns = _exec_parser(parser, case.input_text)
        v, edges = ns["tree"]
        assert len(edges) == v - 1
        assert all(len(t) == 3 for t in edges)  # value_range → (u, v, w)


def test_scalar_roundtrip() -> None:
    field = IOFieldSpec(
        name="k",
        type="int",
        value_range=ConstraintRange(name="k", min_value=1, max_value=50),
    )
    schema = _single(field)
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=3),))
    parser = render_input_parser(schema)
    for case in generate_inputs(contract, schema, seed=3):
        ns = _exec_parser(parser, case.input_text)
        assert ns["k"] == int(case.input_text.strip())


def test_string_roundtrip() -> None:
    field = IOFieldSpec(
        name="word",
        type="string",
        size_range=ConstraintRange(name="word", min_value=3, max_value=10),
    )
    schema = _single(field, output_type="string")
    contract = GeneratorContract(scale_families=(ScaleFamily(name="s", case_count=3),))
    parser = render_input_parser(schema)
    for case in generate_inputs(contract, schema, seed=5):
        ns = _exec_parser(parser, case.input_text)
        assert ns["word"] == case.input_text.strip()


# ---------- 버그 재현 시나리오 (구조적 해소 가드) ----------


def test_weighted_edges_with_trailing_scalars_no_indexerror() -> None:
    """graph 뒤 후행 스칼라(s/t/cap) — 정확히 E 트리플만 소비, 스칼라 보존."""
    schema = IOSchema(
        inputs=(
            IOFieldSpec(
                name="g",
                type="weighted_edges",
                size_range=ConstraintRange(name="V", min_value=4, max_value=4),
                value_range=ConstraintRange(name="w", min_value=1, max_value=9),
            ),
            IOFieldSpec(name="s", type="int"),
            IOFieldSpec(name="t", type="int"),
            IOFieldSpec(name="cap", type="int"),
        ),
        output_type="int",
        output_format="x",
    )
    parser = render_input_parser(schema)
    # dijkstra success 케이스 형상: V E / E 줄 / s / t / cap
    input_text = "4 4\n1 2 5\n2 3 2\n1 3 8\n3 4 3\n1\n4\n100\n"
    ns = _exec_parser(parser, input_text)
    v, e, triples = ns["g"]
    assert (v, e) == (4, 4)
    assert len(triples) == 4
    # 후행 스칼라가 간선으로 오소비되지 않고 정확히 바인딩 (이전 IndexError 원인)
    assert (ns["s"], ns["t"], ns["cap"]) == (1, 4, 100)


def test_redundant_count_scalar_parses_uniformly() -> None:
    """중복 카운트(독립 N + 자기기술 array): 모든 코더가 같게 파싱 → reconcile 합의.

    독립 N 은 토큰 1개로 읽되 array 는 자기 헤더로 읽는다 — N 값이 array 실제 길이와
    달라도 파서는 결정적으로 같은 토큰을 소비(균일 파싱 → 출력 합의).
    """
    schema = IOSchema(
        inputs=(
            IOFieldSpec(name="N", type="int"),
            IOFieldSpec(
                name="amounts",
                type="int_array",
                size_range=ConstraintRange(name="amounts", min_value=1, max_value=9),
            ),
        ),
        output_type="int",
        output_format="x",
    )
    parser = render_input_parser(schema)
    # N=5 인데 배열은 길이 3 (input_gen 이 N 과 배열 길이를 독립 생성하는 모순 상황)
    input_text = "5\n3\n10 20 30\n"
    ns = _exec_parser(parser, input_text)
    assert ns["N"] == 5
    assert ns["amounts"] == [10, 20, 30]  # 배열은 자기 헤더(3)로 정확히 읽음


def test_empty_int_array_no_indexerror() -> None:
    """int_array N=0 (원소 줄 없음, '0' 만) → 빈 리스트, IndexError 없음."""
    field = IOFieldSpec(name="arr", type="int_array")
    schema = _single(field)
    parser = render_input_parser(schema)
    ns = _exec_parser(parser, "0\n")
    assert ns["arr"] == []
