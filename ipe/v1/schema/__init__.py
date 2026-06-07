"""IPE v1 schema — typed structured artifacts (Pydantic v2).

v0 ``ProblemState`` (TypedDict prose) 의 후속. D안 Phase 1 PR-A1 산출.
"""

from __future__ import annotations

from .algorithm_design import AlgorithmDesign, ComplexityBound, EdgeCase, Invariant
from .blueprint import (
    BlueprintFormalization,
    IOFieldSpec,
    IOSchema,
    Narrative,
    NarrativeDraft,
    NarrativeFaithfulnessReport,
    OutputInvariant,
    ProblemBlueprint,
    StrategySeed,
)
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
    "BlueprintFormalization",
    "ComplexityBound",
    "ConstraintRange",
    "EdgeCase",
    "FailedStrategy",
    "FailureMode",
    "IOContract",
    "IOFieldSpec",
    "IOSchema",
    "Invariant",
    "InvariantViolation",
    "IterationContext",
    "IterationRecord",
    "Lesson",
    "Narrative",
    "NarrativeDraft",
    "NarrativeFaithfulnessReport",
    "OutputInvariant",
    "ProblemBlueprint",
    "ProblemSpec",
    "ReconciliationResult",
    "SampleResult",
    "SampleTestCase",
    "SolutionAttempt",
    "SolutionCandidate",
    "StrategySeed",
    "StructuredFeedback",
    "TargetAlgorithm",
    "TargetNode",
    "VerificationResult",
]
