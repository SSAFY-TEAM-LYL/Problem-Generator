"""IPE v1 schema — typed structured artifacts (Pydantic v2).

v0 ``ProblemState`` (TypedDict prose) 의 후속. D안 Phase 1 PR-A1 산출.
"""

from __future__ import annotations

from .algorithm_design import AlgorithmDesign, ComplexityBound, EdgeCase, Invariant
from .iteration_context import FailedStrategy, IterationContext, IterationRecord
from .problem_spec import (
    ConstraintRange,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    TargetAlgorithm,
)
from .solution_attempt import Lesson, SolutionAttempt
from .synthesis import ReconciliationResult, SolutionCandidate
from .verification_result import (
    FailureMode,
    InvariantViolation,
    SampleResult,
    StructuredFeedback,
    TargetNode,
    VerificationResult,
)

__all__ = [
    "AlgorithmDesign",
    "ComplexityBound",
    "ConstraintRange",
    "EdgeCase",
    "FailedStrategy",
    "FailureMode",
    "IOContract",
    "Invariant",
    "InvariantViolation",
    "IterationContext",
    "IterationRecord",
    "Lesson",
    "ProblemSpec",
    "ReconciliationResult",
    "SampleResult",
    "SampleTestCase",
    "SolutionAttempt",
    "SolutionCandidate",
    "StructuredFeedback",
    "TargetAlgorithm",
    "TargetNode",
    "VerificationResult",
]
