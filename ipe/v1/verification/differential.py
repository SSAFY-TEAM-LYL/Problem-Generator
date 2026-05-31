"""Differential tester — golden ↔ brute 차분 (Phase 3 M1, Tier B 핵심 축).

golden 과 (구조적으로 독립인) brute 를 **동일 입력들**에 실행해 출력을 비교한다.

- 일치 = 알고리즘 구현 정확성의 강한 신호 (ICPC/IOI stress-test 실무).
- 불일치 = 둘 중 하나가 틀림 → 문제 reject 신호 (FailureMode.BRUTE_DISAGREEMENT).

RFC §7: differential 만으로는 '상관된 오해'(golden·brute 가 지문을 똑같이 오독)를
못 막는다. 그래서 Tier B 는 differential + problem-class metamorphic + 탈상관 유도
(golden=형식 spec, brute=서사) + 무모호 spec 게이트 의 스택. 본 모듈은 그 중
differential 한 축만 담당한다.

LLM 없음 (deterministic). ``runner`` 주입 — 단위 테스트는 mock 으로 sandbox 없이 검증.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ._exec import (
    DEFAULT_MEMORY_LIMIT_MB as _DEFAULT_MEMORY_LIMIT_MB,
)
from ._exec import (
    DEFAULT_TIME_LIMIT_MS as _DEFAULT_TIME_LIMIT_MS,
)
from ._exec import (
    CodeRunner as DiffRunner,
)
from ._exec import (
    run_code,
)

__all__ = [
    "DiffRunner",
    "DifferentialCase",
    "DifferentialReport",
    "run_differential",
]


@dataclass(frozen=True)
class DifferentialCase:
    """입력 하나에 대한 golden vs brute 비교 결과."""

    input_text: str
    golden_output: str
    brute_output: str
    golden_status: str
    brute_status: str
    agreed: bool


@dataclass(frozen=True)
class DifferentialReport:
    """differential 실행 요약. tier 판정의 입력."""

    cases: tuple[DifferentialCase, ...]

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def disagreements(self) -> tuple[DifferentialCase, ...]:
        return tuple(c for c in self.cases if not c.agreed)

    @property
    def both_ran(self) -> int:
        """golden·brute 가 둘 다 OK 로 끝난 케이스 수 (실효 비교 신호)."""
        return sum(
            1 for c in self.cases if c.golden_status == "OK" and c.brute_status == "OK"
        )

    @property
    def all_agreed(self) -> bool:
        """입력이 1개 이상이고 모든 케이스가 일치할 때만 True.

        입력 0개 = 신호 없음 → False (vacuous 통과 금지, B2B precision).
        """
        return self.total > 0 and len(self.disagreements) == 0


def _normalize(text: str) -> str:
    """출력 정규화 — 줄 단위 trim + 양끝 공백 제거 (사소한 형식차 흡수)."""
    return "\n".join(line.strip() for line in text.strip().splitlines())


def run_differential(
    *,
    golden_code: str,
    brute_code: str,
    inputs: Sequence[str],
    runner: DiffRunner,
    time_limit_ms: int = _DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = _DEFAULT_MEMORY_LIMIT_MB,
) -> DifferentialReport:
    """golden·brute 를 각 입력에 실행해 출력 비교. 한 케이스라도 불일치 시 reject 신호.

    ``agreed`` 는 **둘 다 OK 로 끝나고 정규화 출력이 동일**할 때만 True. 한쪽이라도
    crash/TLE 면 agreed=False (확인 불가 = 보수적으로 불일치 취급).
    """
    cases: list[DifferentialCase] = []
    for inp in inputs:
        g = run_code(runner, golden_code, inp, time_limit_ms, memory_limit_mb)
        b = run_code(runner, brute_code, inp, time_limit_ms, memory_limit_mb)
        g_out = _normalize(g.stdout) if g.status == "OK" else ""
        b_out = _normalize(b.stdout) if b.status == "OK" else ""
        agreed = g.status == "OK" and b.status == "OK" and g_out == b_out
        cases.append(
            DifferentialCase(
                input_text=inp,
                golden_output=g_out,
                brute_output=b_out,
                golden_status=g.status,
                brute_status=b.status,
                agreed=agreed,
            )
        )
    return DifferentialReport(cases=tuple(cases))
