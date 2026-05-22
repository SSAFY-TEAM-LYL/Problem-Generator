"""SolutionAttempt — Coder 출력. 한 번의 implementation 시도.

기존 (v0): ``state["solution_code"]``, ``state["brute_solution_code"]``,
``state["lessons_learned"]`` 가 별도 필드로 흩어져 있음.

v1: 한 attempt 가 단일 immutable model. 여러 attempt 이력은
``IterationContext`` 에 누적.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Lesson(BaseModel):
    """이전 시도에서 학습한 한 줄 교훈. R13 ``lessons_learned`` 의 typed 형태.

    v1 신규: ``signature`` 로 중복 누적 회피 (set semantic).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    signature: str = Field(
        ..., min_length=1, description="중복 dedup 용 짧은 key (해시/요약)"
    )
    content: str = Field(..., min_length=1, description="full lesson 문장")
    from_iter: int = Field(..., ge=0)


class SolutionAttempt(BaseModel):
    """Coder 한 번의 시도. Executor verifier 의 입력.

    v1 핵심: ``code`` 와 ``brute_code`` 가 같은 contract 안에. ``lessons`` 가
    attempt 에 묶임 (어느 시점의 learning state 였는지 추적 가능).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(..., min_length=1, description="golden solution 코드")
    language: Literal["python", "java"] = "python"
    lessons: list[Lesson] = Field(
        default_factory=list, description="이 attempt 작성 시 누적된 lessons"
    )
    brute_code: str | None = Field(
        default=None, description="R15 brute oracle (small N cross-check)"
    )
    iteration: int = Field(..., ge=0)
    coder_fanout_index: int = Field(
        default=0, ge=0, description="R14 best-of-N 안에서의 후보 index"
    )
