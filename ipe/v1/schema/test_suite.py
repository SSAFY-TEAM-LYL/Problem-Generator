"""Test-suite 생성 아티팩트 (Phase 3 M4 — 풀 채점셋).

blueprint-first RFC(§4/§7): frozen blueprint 의 ``io_schema`` + **``GeneratorContract``**
(입력 생성기 계약: 규모 family·엣지·분포)로 입력을 결정론적 생성한다. expected output 은
**미포함**(순환 §7) — verified golden 실행으로 채운다(suite assembler).

artifacts:
- ``ScaleFamily``: 입력 규모 tier (small/large/stress 등) + per-field 범위 + 케이스 수.
- ``EdgeCaseSpec``: 반드시 포함할 엣지 케이스 (정확성 채점 강건성).
- ``GeneratorContract``: 위 둘의 frozen 묶음 — io_schema 와 함께 입력 결정.
- ``GeneratedTestCase``: 생성된 입력 + (golden 으로 후행 채움) expected + 출처 category.
- ``TestSuite``: assembled 풀셋 — verified golden 으로 expected 채운 (in, out) 배터리.

모두 frozen + extra=forbid (schema 컨벤션). ``ProblemBlueprint``/state 무변경 —
additive 신규 (생성/배선 노드는 후속 step).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .problem_spec import ConstraintRange


class ScaleFamily(BaseModel):
    """입력 규모 tier — 결정론적 생성기가 family 별로 입력 생성.

    ``field_bounds`` 는 io_schema 의 전체 범위를 이 tier 로 **좁힌다** (예: 'small'
    은 N∈[1,10], 'large' 는 N∈[1e4,1e5]). 비우면 io_schema 기본 범위 사용.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        ..., min_length=1, description="tier 이름 (예: 'small'/'large'/'stress')"
    )
    case_count: int = Field(..., gt=0, description="이 family 에서 생성할 케이스 수")
    field_bounds: tuple[ConstraintRange, ...] = Field(
        default=(), description="이 tier 의 per-field 크기/값 범위 (io_schema 범위 좁힘)"
    )
    description: str = ""


class EdgeCaseSpec(BaseModel):
    """반드시 포함할 엣지 케이스 명세 — 정확성 채점 강건성 (경계/퇴화 입력)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        ..., min_length=1, description="엣지 이름 (예: 'empty'/'single'/'max_size')"
    )
    description: str = ""


class GeneratorContract(BaseModel):
    """frozen 입력 생성기 계약 (RFC §4/§7) — io_schema 와 함께 입력을 결정.

    **expected output 은 포함하지 않음**(순환 §7): 입력은 schema+contract 에서 결정론적
    생성 가능하나 정답은 golden 실행이 있어야 안다 → suite assembler 가 채운다.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scale_families: tuple[ScaleFamily, ...] = Field(
        ..., min_length=1, description="커버할 규모 tier (>=1)"
    )
    edge_cases: tuple[EdgeCaseSpec, ...] = ()
    determinism_seed: int | None = Field(
        default=None, description="재현가능 생성 seed (None=비결정/노드 선택)"
    )
    notes: str = ""

    @property
    def total_planned_cases(self) -> int:
        """계획된 총 케이스 수 = scale_families case_count 합 + edge_cases 각 1."""
        return sum(f.case_count for f in self.scale_families) + len(self.edge_cases)


class GeneratedTestCase(BaseModel):
    """생성된 입력 + (golden 으로 채운) expected. bootstrap(§7): expected 후행.

    ``expected_output=None`` = golden 미실행(pending), ``str`` = 채워짐. ``category``
    는 출처(scale_family/edge_case name) — 채점셋 진단·분포 추적용.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_text: str = Field(..., min_length=1)
    category: str = Field(
        ..., min_length=1, description="출처 (scale_family/edge_case name)"
    )
    expected_output: str | None = Field(
        default=None, description="None=golden 미실행(pending), str=채워짐"
    )
    golden_elapsed_ms: int | None = Field(
        default=None,
        ge=0,
        description="이 케이스의 golden 실행시간 — 백엔드 TL 산정 근거 (계약 v1.0)",
    )


class TestSuite(BaseModel):
    """assembled 풀 채점셋 — verified golden 으로 expected 채운 (in, out) 배터리.

    ``is_assembled`` 이 True 면 모든 케이스의 expected 가 채워진 출하가능 채점셋.
    """

    # 도메인 이름이 'Test' 로 시작 → pytest 가 테스트 클래스로 오인 수집하지 않게.
    __test__ = False

    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: tuple[GeneratedTestCase, ...] = Field(..., min_length=1)
    golden_origin: str | None = Field(
        default=None, description="expected 를 채운 golden 출처 (provenance)"
    )

    @property
    def is_assembled(self) -> bool:
        """모든 케이스의 expected 가 채워졌나 (golden 실행 완료)."""
        return all(c.expected_output is not None for c in self.cases)
