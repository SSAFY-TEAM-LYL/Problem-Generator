"""난이도 calibration 아티팩트 (RFC R4 — v2 사후 난이도 판별).

v0 Evaluator(P9)의 ``difficulty_label``/``reasoning``/``factors``/
``calibration_anchors`` 를 typed 구조로 되살린다. BOJ 표준 난이도 anchor
(``ipe.calibration``)와 비교해 **사후 측정**한다 — 파이프라인 그래프는 RFC 설계상
난이도-agnostic 이고, 본 아티팩트는 완성 패키지의 **사후 주석**(출하 게이트 아님)이다.

frozen + extra=forbid (schema 컨벤션). additive 신규 — 기존 스키마 무변경.
"""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

# BOJ 표준 난이도 티어 (낮음→높음). label = "<Tier> <Rank>" (예: "Gold IV").
DifficultyTier = Literal["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Ruby"]
_TIERS: tuple[str, ...] = (
    "Bronze",
    "Silver",
    "Gold",
    "Platinum",
    "Diamond",
    "Ruby",
)


class DifficultyFactors(BaseModel):
    """난이도 판단 근거 요소 (v0 evaluator factors 와 동형)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    algorithm: str = Field(..., min_length=1)  # 지배 알고리즘 (예: "dijkstra")
    complexity: str = Field(..., min_length=1)  # 시간복잡도 (예: "O((V+E) log V)")
    n_max: int | None = None  # 주요 입력 규모 상한 (없으면 None)
    data_structures: tuple[str, ...] = ()


class DifficultyReport(BaseModel):
    """사후 난이도 calibration 결과 — BOJ 티어 라벨 + 근거 + 인용 anchor.

    ``label`` 은 "Gold IV" 형식(티어 + 로마숫자 등급). ``tier`` 는 label 선두에서
    파생하는 computed field — LLM 은 label 만 산출하고 티어 그룹은 결정론적으로
    유도된다(이중 필드 모순 제거). label 선두가 BOJ 티어가 아니면 reject(왜곡된
    구조화 출력 조기 차단). ``reasoning`` 에는 비교에 쓴 anchor id 를 명시한다.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(..., min_length=1)  # "Gold IV"
    reasoning: str = Field(..., min_length=1)  # 인용 anchor id 명시 (사후 검수 가능)
    factors: DifficultyFactors
    calibration_anchors: tuple[str, ...] = ()  # 비교에 쓴 anchor id (로드 집합 교집합)

    @field_validator("label")
    @classmethod
    def _label_starts_with_known_tier(cls, v: str) -> str:
        parts = v.split()
        head = parts[0] if parts else ""
        if head not in _TIERS:
            msg = f"label '{v}' 선두 티어가 BOJ 티어 집합 {_TIERS} 에 없음"
            raise ValueError(msg)
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tier(self) -> DifficultyTier:
        """label 선두에서 파생한 티어 그룹 (필터·집계용, model_dump 에 포함)."""
        return cast(DifficultyTier, self.label.split()[0])
