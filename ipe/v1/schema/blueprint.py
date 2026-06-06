"""Blueprint-first 모델링 layer 아티팩트 (Phase 3 M3).

blueprint-first 노선(`docs/rfc/phase3_blueprint-first-generation.md`): formal schema 를
**먼저 freeze** 하고, golden/brute/test 가 prose 가 아닌 그 schema 를 읽는다. narrative
는 마지막 렌더링 단계로 강등 + round-trip 으로 충실성 검증. 목적: 상관오독(메인 §7
핵심 위협)을 사후 게이트가 아니라 **생성 구조**로 방어.

artifacts:
- ``ProblemBlueprint``: Formalizer 가 freeze 하는 formal 계약 (io_schema +
  output_invariants + 숨은 reduction_core). frozen=True 자체가 freeze.
- ``Narrative``: late artifact — frozen blueprint 의 시나리오 렌더(은닉/직접).
- ``NarrativeFaithfulnessReport``: round-trip 결과 (왜곡=reject, 은닉=OK).

``ProblemSpec`` (problem_spec.py) 와의 관계: blueprint 은 freeze 되는 **상위 formal
계약**, ProblemSpec 은 그로부터 파생되는 solver/executor 입력 contract. ``generator_
contract`` (입력 생성기 제약) 은 입력 생성 milestone(M4)으로 이연.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .problem_spec import ConstraintRange, TargetAlgorithm

IOFieldType = Literal[
    "int",
    "int_array",
    "int_matrix",
    "float",
    "string",
    "bool",
    "weighted_edges",
    "tree_edges",
    "grid",
]

OutputType = Literal["int", "int_array", "float", "bool", "string", "yes_no"]


class IOFieldSpec(BaseModel):
    """입력 한 필드의 formal 명세 — 타입 + 크기/값 범위 (prose 아님)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., min_length=1, description="필드 이름 (예: 'N', 'edges')")
    type: IOFieldType
    size_range: ConstraintRange | None = Field(
        default=None, description="배열/행렬/그래프의 원소·정점 수 범위"
    )
    value_range: ConstraintRange | None = Field(
        default=None, description="수치 값 범위 (가중치/원소값 등)"
    )
    description: str = ""


class IOSchema(BaseModel):
    """입력 구조/타입/범위 + 출력 타입/형식 — frozen blueprint 의 핵심 formal 면."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inputs: tuple[IOFieldSpec, ...] = Field(..., min_length=1)
    output_type: OutputType
    output_format: str = Field(..., min_length=1, description="출력 인쇄 형식")


class OutputInvariant(BaseModel):
    """출력이 항상 만족할 관계 — symbolic invariant 후보 (verifier schema 파생 단초)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(
        ...,
        min_length=1,
        description="invariant 종류 (예: non_negative / monotonic / sum_conserved)",
    )
    description: str = Field(..., min_length=1)


class ProblemBlueprint(BaseModel):
    """blueprint-first 의 **frozen formal 계약** (M3 Formalizer 산출).

    golden/brute/test 가 이 schema 를 읽는다 (prose 아님). ``model_config``
    frozen=True 자체가 freeze 계약 — 생성 후 불변. ``reduction_core`` 는 숨은
    알고리즘(solver 는 모르고 은닉 narrative 만 봄, 내부 artifact 엔 명시).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reduction_core: TargetAlgorithm = Field(
        ..., description="숨은 알고리즘/환원 (solver 모름, 내부 명시)"
    )
    composition: tuple[TargetAlgorithm, ...] = Field(
        default=(), description="reduction_core 외 추가 합성 기법 (기법 합성)"
    )
    domain: str = Field(
        ..., min_length=1, description="narrative 렌더용 현실 도메인 (예: 'logistics')"
    )
    io_schema: IOSchema
    output_invariants: tuple[OutputInvariant, ...] = ()


class Narrative(BaseModel):
    """late artifact — frozen blueprint 의 시나리오 렌더링 (M3 Narrative Author).

    ``hidden=True`` 면 알고리즘 은닉 렌더(full/B2B), ``False`` 면 직접 기술
    (canonical/B2C 토픽드릴). 은닉은 *생성 순서* 가 아니라 **렌더링 선택**.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario: str = Field(..., min_length=1, description="현실 시나리오 지문")
    hidden: bool = Field(..., description="알고리즘 은닉 렌더 여부")
    domain: str = Field(..., min_length=1)


class NarrativeFaithfulnessReport(BaseModel):
    """round-trip 충실성 결과 (M3) — narrative 재형식화 schema vs frozen blueprint diff.

    정보 *은닉*(누락 의도)은 distortion 아님; 정보 *왜곡*(다른 문제 기술)만 reject.
    ``faithful=False`` 면 narrative 재생성 (싼 반복).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    faithful: bool = Field(
        ..., description="재형식화가 frozen blueprint 와 일치 (왜곡 없음)"
    )
    distortions: tuple[str, ...] = Field(
        default=(), description="왜곡 근거 (reject 사유, 사람이 읽는 설명)"
    )
