"""Tier B 검증 컴포넌트 (Phase 3 M1) — differential + metamorphic + tier 판정.

기존 ``ipe/v1/verifiers/`` (Tier A, algorithm-specific symbolic) 와 분리.
RFC §7: 복잡/은닉 문제에서 symbolic 이 안 통하는 구간을 golden↔brute 차분 +
problem-class metamorphic 으로 검증. B2B 는 Tier B 이상만 출하.
"""

from __future__ import annotations

from .differential import (
    DifferentialCase,
    DifferentialReport,
    DiffRunner,
    run_differential,
)
from .metamorphic import (
    MetamorphicReport,
    MetamorphicResult,
    check_determinism,
    check_well_formed,
    run_metamorphic,
)
from .tier import (
    Tier,
    TierAxis,
    TierVerdict,
    classify,
    symbolic_axis,
)

__all__ = [
    "DiffRunner",
    "DifferentialCase",
    "DifferentialReport",
    "MetamorphicReport",
    "MetamorphicResult",
    "Tier",
    "TierAxis",
    "TierVerdict",
    "check_determinism",
    "check_well_formed",
    "classify",
    "run_differential",
    "run_metamorphic",
    "symbolic_axis",
]
