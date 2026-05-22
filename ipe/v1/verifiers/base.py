"""SymbolicVerifier Protocol + module-level dispatch registry.

PR-A3 의 executor 가 ``get_verifier(spec.target_algorithm)`` 로 dispatch.
Phase 1 = Dijkstra 하나. Phase 2 에서 LIS/SegmentTree 추가 시 같은 registry 에
``register_verifier(...)`` 호출만 추가.
"""

from __future__ import annotations

from typing import Protocol

from ..schema import (
    AlgorithmDesign,
    InvariantViolation,
    ProblemSpec,
    SolutionAttempt,
    TargetAlgorithm,
)


class SymbolicVerifier(Protocol):
    """Algorithm-specific 결정론적 verifier.

    한 algorithm 의 수학적 invariants 를 코드 실행 결과로 검증. LLM 판단과 무관 —
    fixture 가 통과하면 정답 보장.
    """

    target_algorithm: TargetAlgorithm

    def verify(
        self,
        spec: ProblemSpec,
        design: AlgorithmDesign,
        attempt: SolutionAttempt,
        sample_outputs: list[str],
    ) -> list[InvariantViolation]:
        """Invariant 위반 list 반환. 빈 list = 모든 invariant 통과.

        ``sample_outputs[i]`` 는 ``spec.sample_testcases[i].input_text`` 를
        ``attempt.code`` 로 실행한 stdout (trim). PR-A3 의 executor 가 호출.
        """
        ...


_REGISTRY: dict[TargetAlgorithm, SymbolicVerifier] = {}


def register_verifier(verifier: SymbolicVerifier) -> None:
    """verifier instance 등록. PR-A3 executor 가 dispatch 에 사용.

    같은 ``target_algorithm`` 으로 재등록 시 기존 verifier 교체 — 테스트 격리
    또는 향후 verifier 교체 사용.
    """
    _REGISTRY[verifier.target_algorithm] = verifier


def get_verifier(algo: TargetAlgorithm) -> SymbolicVerifier | None:
    """등록된 verifier 반환. 없으면 None (executor 가 graceful skip)."""
    return _REGISTRY.get(algo)


def clear_registry() -> None:
    """테스트 격리 용. 프로덕션 호출 금지."""
    _REGISTRY.clear()
