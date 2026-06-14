"""sample_filler 노드 (v2) — canonical golden 실행으로 sample expected 채움.

**사용자 원칙** (정답은 golden 실행으로 부트스트랩, RFC §7): spec_bridge 는 sample
**input 만** 저작하고 expected 를 LLM 으로 손계산하지 않는다. reconcile 로 확정된
canonical golden 을 각 sample input 에 실행해 stdout 을 expected 로 채운다 —
suite_assembler 와 동일 원칙 (LLM 토큰 0, ``run_code`` 재사용).

이로써 ① LLM 직접 토큰 expected 생성 제거 (N 큰 입출력은 스크립트/golden 으로, 약점
저격 TC 만 예외) ② verification ``sample_mismatch`` (LLM 손계산 오답) 결함 제거. golden
정확성은 reconcile(golden↔brute differential) + symbolic verifier 가 보장한다.

reconcile 이 이미 같은 sample input 으로 golden↔brute differential 을 통과시킨 뒤라
이 노드 시점엔 golden 이 그 입력들을 성공 실행한다. 방어적으로, golden 실행이 실패한
sample 은 **원본(빈 expected) 그대로 유지**한다 — drop 하면 ``ProblemSpec`` 의 최소 3개
제약을 깨 재검증 crash 가 나므로, 길이를 보존하고 그런 sample 은 하류 executor 가
형식 불일치로 fail 처리하게 둔다. 그래프상 reconcile 채택 경로 뒤에만 배선되므로
``canonical_code`` 는 존재한다(방어적으로 None 가드).
"""

from __future__ import annotations

from collections.abc import Callable

from ipe.v1.verification._exec import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIME_LIMIT_MS,
    CodeRunner,
    run_code,
)

from ..state import V2State


def make_sample_filler_node(*, runner: CodeRunner) -> Callable[[V2State], V2State]:
    """factory — reconcile canonical golden 으로 sample expected 채움. LLM 없음.

    test 는 mock runner 주입 (sandbox 없이 결정론 검증). 실행 OK 인 sample 만
    expected 채워 유지하고 실패분은 drop.
    """

    def node(state: V2State) -> V2State:
        spec = state.spec
        rec = state.reconciliation
        if spec is None or rec is None or rec.canonical_code is None:
            return state  # reject 경로면 도달 안 함 — 방어적 no-op
        golden = rec.canonical_code
        filled = []
        for sample in spec.sample_testcases:
            result = run_code(
                runner,
                golden,
                sample.input_text,
                DEFAULT_TIME_LIMIT_MS,
                DEFAULT_MEMORY_LIMIT_MB,
            )
            if result.status == "OK":
                filled.append(
                    sample.model_copy(
                        update={"expected_output": result.stdout.strip()}
                    )
                )
            else:
                # golden 파싱 실패(형식 불일치) — 원본 유지(길이 보존, min 3 제약).
                # executor 가 같은 입력에서 또 실패해 fail_verification 으로 잡는다.
                filled.append(sample)
        new_spec = spec.model_copy(update={"sample_testcases": filled})
        return state.model_copy(update={"spec": new_spec})

    return node
