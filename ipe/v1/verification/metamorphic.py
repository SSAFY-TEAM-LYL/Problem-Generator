"""Metamorphic checker — problem-agnostic 불변 검사 (Phase 3 M1, Tier B 보강축).

(가) 결정: **범용 관계만** 먼저 — per-problem 지식 0:

- ``determinism``: 같은 입력 재실행 → 동일 출력. 불안정 golden = 불안정 정답지
  (채용 시험에서 치명). 미시드 random / 해시 순서 / 시간 의존 등을 잡는다.
- ``well_formed``: status OK + 비어있지 않은 stdout + error leak(Traceback) 없음.

강한 class별 관계(feasibility / optimality bound)는 **step 4 측정에서 differential
+ 범용 metamorphic 만으로 Tier B ≈ Tier A 가 안 될 때만** 투자한다
(measurement-first, per-algo 벽 회피).

LLM 없음 (deterministic). ``runner`` 주입 — 단위 테스트는 mock.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ._exec import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIME_LIMIT_MS,
    CodeRunner,
    run_code,
)

_DEFAULT_REPEATS = 2
_ERROR_MARKERS = ("Traceback (most recent call last)",)


@dataclass(frozen=True)
class MetamorphicResult:
    """한 (관계, 입력) 검사 결과."""

    relation: str  # "determinism" | "well_formed"
    input_text: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class MetamorphicReport:
    """metamorphic 검사 요약. tier 판정의 입력."""

    results: tuple[MetamorphicResult, ...]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def violations(self) -> tuple[MetamorphicResult, ...]:
        return tuple(r for r in self.results if not r.passed)

    @property
    def all_passed(self) -> bool:
        """검사가 1개 이상이고 위반이 없을 때만 True (vacuous 통과 금지)."""
        return self.total > 0 and len(self.violations) == 0


def check_determinism(
    *,
    code: str,
    inputs: Sequence[str],
    runner: CodeRunner,
    repeats: int = _DEFAULT_REPEATS,
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> list[MetamorphicResult]:
    """각 입력을 ``repeats`` 회 실행 → 출력이 전부 동일해야 한다."""
    results: list[MetamorphicResult] = []
    for inp in inputs:
        seen: set[str] = set()
        for _ in range(max(2, repeats)):
            r = run_code(runner, code, inp, time_limit_ms, memory_limit_mb)
            seen.add(r.stdout.strip() if r.status == "OK" else f"<{r.status}>")
        stable = len(seen) == 1
        detail = "" if stable else f"{repeats} runs differ: {sorted(seen)[:3]}"
        results.append(MetamorphicResult("determinism", inp, stable, detail))
    return results


def check_well_formed(
    *,
    code: str,
    inputs: Sequence[str],
    runner: CodeRunner,
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> list[MetamorphicResult]:
    """출력이 잘 형성됐는지 — status OK + 비어있지 않음 + Traceback leak 없음."""
    results: list[MetamorphicResult] = []
    for inp in inputs:
        r = run_code(runner, code, inp, time_limit_ms, memory_limit_mb)
        ok = r.status == "OK"
        nonempty = bool(r.stdout.strip())
        no_leak = not any(marker in r.stdout for marker in _ERROR_MARKERS)
        passed = ok and nonempty and no_leak
        detail = (
            ""
            if passed
            else f"status={r.status} nonempty={nonempty} no_leak={no_leak}"
        )
        results.append(MetamorphicResult("well_formed", inp, passed, detail))
    return results


def run_metamorphic(
    *,
    code: str,
    inputs: Sequence[str],
    runner: CodeRunner,
    repeats: int = _DEFAULT_REPEATS,
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> MetamorphicReport:
    """범용 관계(well_formed + determinism)를 모든 입력에 적용한 종합 report."""
    results = check_well_formed(
        code=code,
        inputs=inputs,
        runner=runner,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
    )
    results += check_determinism(
        code=code,
        inputs=inputs,
        runner=runner,
        repeats=repeats,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
    )
    return MetamorphicReport(results=tuple(results))
