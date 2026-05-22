"""VerificationResult — Executor (Phase A + symbolic verifier) 결과의 typed taxonomy.

기존 (v0): ``state["execution_results"]``, ``state["final_status"]``,
``state["feedback_message"]`` 가 prose 로 흩어짐. 실패 모드 enum 없어서 fix loop
가 prose parsing 의존.

v1 핵심: structured feedback. ``FailureMode`` enum 으로 fix loop 의 routing 결정
론화 (D안 H1 — fix loop ``budget_exhausted`` 감소 목표).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FailureMode(StrEnum):
    """v1 실패 분류. 노드 routing 의 결정론적 key.

    enum 값은 prose feedback 의 prefix 와 1:1 매핑. v0 ``last_failed_node`` +
    ``feedback_message`` 를 typed enum 으로 결합.
    """

    NONE = "none"
    SAMPLE_MISMATCH = "sample_mismatch"
    SAMPLE_CRASH = "sample_crash"
    SAMPLE_TIMEOUT = "sample_timeout"
    INVARIANT_VIOLATION = "invariant_violation"
    BRUTE_DISAGREEMENT = "brute_disagreement"
    COMPILE_ERROR = "compile_error"
    UNKNOWN = "unknown"


class SampleResult(BaseModel):
    """Phase A 한 sample 의 결과."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int = Field(..., ge=0)
    passed: bool
    expected_output: str
    actual_output: str
    stderr: str = ""
    elapsed_ms: int = Field(..., ge=0)


class InvariantViolation(BaseModel):
    """Symbolic verifier 가 reject 한 invariant 의 evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    invariant_kind: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    evidence: dict[str, str] = Field(
        default_factory=dict,
        description="violation 의 구체 (input, output, expected). value 는 string화",
    )


class StructuredFeedback(BaseModel):
    """Fix loop 의 routing key. prose 가 아닌 structured.

    v1 핵심: ``target_node`` + ``actionable_hint`` 로 결정론적 routing. LLM
    prompt 에는 render 단계에서 자연어로 변환되지만, routing 결정 자체는 enum.
    ``blocking_signature`` 는 oscillation detection 용.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_node: str = Field(
        ...,
        min_length=1,
        description="다음 fix 시도 노드 (architect/designer/coder/auditor/generator)",
    )
    actionable_hint: str = Field(..., min_length=1, description="구체적 수정 방향")
    blocking_signature: str = Field(
        ..., min_length=1, description="oscillation detection 용 short hash key"
    )


class VerificationResult(BaseModel):
    """Executor 의 종합 출력. 다음 fix loop 의 결정 anchor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    overall_pass: bool
    failure_mode: FailureMode
    sample_results: list[SampleResult] = Field(default_factory=list)
    invariant_violations: list[InvariantViolation] = Field(default_factory=list)
    feedback: StructuredFeedback | None = Field(
        default=None, description="``overall_pass=False`` 일 때만 set"
    )
    iteration: int = Field(..., ge=0)
