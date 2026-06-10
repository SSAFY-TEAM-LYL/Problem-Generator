"""suite assembler — verified golden 실행으로 pending TestSuite 의 expected 채움 (M4 step4).

step3 입력 생성기가 만든 pending TestSuite(expected=None)의 각 입력에 **검증된 golden**
(reconciled canonical, verification 통과)을 sandbox 실행해 stdout 을 expected 로 채운다
(RFC §7: 정답은 golden 실행으로 부트스트랩). 실행 도구는 Tier B 공용 ``run_code`` 재사용
(moat, 중복 0).

golden 이 실행 못하는 입력(crash/timeout)은 **drop** — 입력 직렬화↔골든 파서 불일치
또는 골든 버그의 신호다. assembled 케이스 수 / pending 수 = 규약 정합 비율(step5 anchor).
전부 실패면 ValueError (형식 불일치 가능 — known item).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ipe.v1.schema import GeneratedTestCase, TestSuite
from ipe.v1.verification._exec import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIME_LIMIT_MS,
    run_code,
)

if TYPE_CHECKING:
    from ipe.v1.verification._exec import CodeRunner


def assemble_suite(
    pending: TestSuite,
    golden_code: str,
    *,
    runner: CodeRunner,
    golden_origin: str,
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> TestSuite:
    """golden 을 각 입력에 실행 → expected 채운 assembled TestSuite.

    실행 OK 인 케이스만 expected 채워 포함(나머지 drop). 전부 실패면 ValueError.
    ``golden_origin`` 은 provenance(어느 golden 이 정답을 만들었나).
    """
    filled: list[GeneratedTestCase] = []
    for case in pending.cases:
        result = run_code(
            runner,
            golden_code,
            case.input_text,
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )
        if result.status == "OK":
            filled.append(
                case.model_copy(update={"expected_output": result.stdout.strip()})
            )
    if not filled:
        msg = (
            "assemble_suite: golden 이 생성 입력을 하나도 실행하지 못함 "
            "(입력 직렬화↔골든 파서 불일치 가능)"
        )
        raise ValueError(msg)
    return TestSuite(cases=tuple(filled), golden_origin=golden_origin)
