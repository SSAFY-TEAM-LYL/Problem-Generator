"""병렬 solution synthesis 아티팩트 (Phase 3 M2) — fan-out 후보 + fan-in 집계.

RFC §6 Solution Synthesis 스테이지의 typed I/O 계약:
- ``SolutionCandidate``: Golden×K / Brute 가 각자 emit 하는 후보 (fan-out). reducer
  채널(``Annotated[list, operator.add]``)에 누적된다.
- ``ReconciliationResult``: Reconciler(N5, 코드)가 K golden + brute 상호 일치를
  differential 로 확인하고 canonical 을 채택한 결과 (fan-in).

기존 ``SolutionAttempt`` 는 단일경로(canonical mode) 용으로 유지 (RFC §8).
``SolutionCandidate`` 는 병렬 경로용 — ``origin`` 으로 모델/전략 독립성을 추적
(brute 독립성 4조건 §7.4 의 '모델 독립').
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SolutionCandidate(BaseModel):
    """병렬 solution synth 한 후보 — Golden 또는 Brute 가 emit (fan-out 단위).

    ``role`` 로 golden/brute 구분, ``origin`` 으로 생성 출처(모델 family 또는
    전략 라벨)를 기록해 differential 의 독립성 전제를 추적한다.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["golden", "brute"]
    origin: str = Field(
        ..., min_length=1, description="생성 출처 라벨 (예: 'opus' / 'sonnet' / 'naive')"
    )
    code: str = Field(..., min_length=1, description="후보 solution 코드")
    language: Literal["python", "java"] = "python"
    fanout_index: int = Field(default=0, ge=0, description="fan-out 내 후보 index")


class ReconciliationResult(BaseModel):
    """Reconciler(N5) 출력 — K golden + brute 상호 일치 판정 + canonical 채택.

    ``all_agree`` 이면 ``canonical_code`` 채택(adopted_origin 표기), 불일치면
    ``canonical_code=None`` + ``disagreements`` 에 근거. 이후 검증 스테이지가
    canonical 을 입력으로 사용 (불일치는 reject 신호).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_count: int = Field(..., ge=0, description="reconcile 에 들어온 후보 수")
    all_agree: bool = Field(..., description="모든 golden + brute 가 샘플에서 일치")
    canonical_code: str | None = Field(
        default=None, description="채택된 canonical golden 코드 (불일치 시 None)"
    )
    adopted_origin: str | None = Field(
        default=None, description="canonical 로 채택된 후보의 origin"
    )
    disagreements: tuple[str, ...] = Field(
        default=(), description="불일치 근거 (사람이 읽는 설명)"
    )
