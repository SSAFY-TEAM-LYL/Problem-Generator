"""Sandbox stdin large-input threshold tests — R-sandbox Step 1.

배경: Sprint 3 e2e Run 7/8 0/5 의 진짜 병목 — Phase C stress에서 솔루션이
22ms RTE (Python interpreter 시작 전). 동일 솔루션 + 동일 입력이 로컬에서는
40ms exit 0. RCA: `docs/improvements/2026-05-14_sandbox-infra-rca.md`.

본 테스트는 ``RlimitRunner.run()``을 e2e 우회하여 직접 호출:
- stdin size 점진 (1KB / 100KB / 500KB / 875KB / 2MB)
- 어느 size부터 RTE/MLE 발생하는지 임계 측정
- macOS Darwin RLIMIT_AS 무시 vs Linux RLIMIT_AS 차이 측정

전략: 솔루션은 ``sys.stdin.buffer.read()``로 모든 input을 한번에 읽고 길이
출력만 함 — algorithm 영향 0, 순수 sandbox stdin 처리 능력 측정.

@pytest.mark.slow — 실제 subprocess + RLIMIT 적용으로 CI 기본 실행에서 제외
가능. R-sandbox 진단 시 ``pytest -m slow`` 수동 실행.
"""

from __future__ import annotations

import sys

import pytest

from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.sandbox.runner import RunSpec

pytestmark = pytest.mark.slow

# 솔루션: stdin 모두 읽고 byte 수만 출력 — 순수 stdin 처리 능력 측정.
# algorithm/parsing overhead 0, RTE는 sandbox infra 한계로만 발생.
_STDIN_LEN_PROBE = (
    "import sys; "
    "data = sys.stdin.buffer.read(); "
    "sys.stdout.write(str(len(data)))"
)

# 측정 size 점진. 각 size는 N=200000 + value range로 e2e 실측한 범위:
# - 1KB:    sample testcase 일반 크기
# - 100KB:  RANDOM_MEDIUM 카테고리 상한
# - 500KB:  R10 cap (1.5MB MAX_STRESS 권장)의 1/3
# - 875KB:  Run 8 Two Sum seed=1 실측 (878566 bytes, RTE 발생)
# - 2MB:    R10 hard cap (R10 통과 한도)
_SIZE_CASES = [
    ("1KB", 1024),
    ("100KB", 100 * 1024),
    ("500KB", 500 * 1024),
    ("875KB", 875 * 1024),
    ("2MB", 2 * 1024 * 1024),
]


def _make_stdin(num_bytes: int) -> str:
    """num_bytes 크기의 ASCII stdin 생성 — 정수 토큰들로 채움 (실측 input과 유사 분포)."""
    # 정수 + space 패턴이 ~7 bytes per token → token count 추정
    token = "1234567 "  # 8 bytes
    repeats = (num_bytes // len(token)) + 1
    data = token * repeats
    return data[:num_bytes]


@pytest.mark.parametrize("label,size", _SIZE_CASES, ids=[s[0] for s in _SIZE_CASES])
def test_rlimit_stdin_size_threshold(label: str, size: int) -> None:
    """RlimitRunner가 ``size`` bytes stdin을 처리할 수 있는지 측정.

    DEFAULT_MEMORY_LIMIT_MB(512) + time_limit 5000ms 기준 — e2e Phase C와 동일.

    측정값:
    - status: OK / RTE / TLE / MLE
    - elapsed_ms
    - stderr 내용

    임계 확정: 어느 size부터 status != "OK" 발생.
    """
    runner = RlimitRunner()
    stdin_text = _make_stdin(size)
    assert len(stdin_text) == size, f"stdin generation off — expected {size}, got {len(stdin_text)}"

    spec = RunSpec(
        cmd=[sys.executable, "-c", _STDIN_LEN_PROBE],
        cwd="/tmp",
        stdin=stdin_text,
        time_limit_ms=5000,
        memory_limit_mb=512,
    )
    res = runner.run(spec)

    # 측정값 출력 — 본 테스트는 임계 발견 용도라 fail시에도 정보 노출
    print(
        f"\n[stdin {label}={size}b] status={res.status} "
        f"elapsed_ms={res.elapsed_ms} stdout_len={len(res.stdout or '')} "
        f"stderr={(res.stderr or '')[:200]!r}"
    )

    # 정상 OK 시: stdout = stdin len (probe 정합성)
    if res.status == "OK":
        assert res.stdout.strip() == str(size), (
            f"probe output mismatch: stdin {size}b → stdout {res.stdout!r}"
        )


def test_rlimit_stdin_5mb_should_fail() -> None:
    """5MB stdin — R10 cap(2MB) 위반 size로 sandbox 거동 측정 (기대: RTE 또는 truncation).

    e2e에서는 R10 generator cap으로 차단되지만, sandbox 자체가 5MB까지 어떻게
    처리하는지 확인 — RLIMIT_AS / pipe buffer 한도 데이터.
    """
    runner = RlimitRunner()
    size = 5 * 1024 * 1024
    stdin_text = _make_stdin(size)

    spec = RunSpec(
        cmd=[sys.executable, "-c", _STDIN_LEN_PROBE],
        cwd="/tmp",
        stdin=stdin_text,
        time_limit_ms=10000,
        memory_limit_mb=512,
    )
    res = runner.run(spec)
    print(
        f"\n[stdin 5MB={size}b] status={res.status} "
        f"elapsed_ms={res.elapsed_ms} stderr={(res.stderr or '')[:200]!r}"
    )
    # 5MB는 RLIMIT_AS 512MB 안에서 Python에 부담 — RTE/MLE 또는 OK 모두 valid 측정
    # 본 테스트는 measurement only — assertion 0


def test_rlimit_stdin_2mb_with_increased_memory() -> None:
    """2MB stdin + memory_limit 2048MB — Python interpreter 여유 ↑ 시 RTE 회피되는지.

    가설: RLIMIT_AS 512MB는 Python interpreter(~50MB) + 2MB stdin buffer +
    user code dict/list overhead로 borderline. 2048MB로 ↑하면 RTE 회피.
    """
    runner = RlimitRunner()
    size = 2 * 1024 * 1024
    stdin_text = _make_stdin(size)

    spec = RunSpec(
        cmd=[sys.executable, "-c", _STDIN_LEN_PROBE],
        cwd="/tmp",
        stdin=stdin_text,
        time_limit_ms=10000,
        memory_limit_mb=2048,
    )
    res = runner.run(spec)
    print(
        f"\n[stdin 2MB + 2048MB mem] status={res.status} "
        f"elapsed_ms={res.elapsed_ms} stderr={(res.stderr or '')[:200]!r}"
    )
    # memory ↑ 시 OK 도달하면 RLIMIT_AS 가설 확정


def test_rlimit_parallel_subprocess_race() -> None:
    """병렬 ThreadPoolExecutor 4 workers — Phase C와 동일 패턴 race 재현.

    핵심 발견 (R-sandbox Step 1): sequential 호출 4회는 모두 OK이지만, 동일
    호출을 ``ThreadPoolExecutor(max_workers=4)``로 동시 실행 시 일부 case가
    RTE 발생. stderr 비어있음 — Python interpreter 시작 전 abort.

    이는 e2e Phase C의 ``PHASE_C_WORKERS=4`` 패턴과 정확히 일치.
    ``subprocess.Popen + preexec_fn(setrlimit)`` 호출이 thread-safe하지 않거나
    OS 자원 race 발생.

    본 테스트는 race 재현 — fail 횟수 측정 (assertion 없음, observability).
    """
    from concurrent.futures import ThreadPoolExecutor

    runner = RlimitRunner()
    # 875KB stdin × 4 parallel — e2e Phase C max_workers=4와 동일
    stdin_text = _make_stdin(875 * 1024)

    def _run_one(idx: int) -> tuple[int, str, int]:
        spec = RunSpec(
            cmd=[sys.executable, "-c", _STDIN_LEN_PROBE],
            cwd="/tmp",
            stdin=stdin_text,
            time_limit_ms=5000,
            memory_limit_mb=512,
        )
        res = runner.run(spec)
        return idx, res.status, res.elapsed_ms

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_run_one, i) for i in range(4)]
        results = [fut.result() for fut in futures]

    rte_count = sum(1 for _, status, _ in results if status != "OK")
    print(
        f"\n[parallel 4×875KB] RTE/fail count: {rte_count}/4. "
        f"Details: {results}"
    )
    # observability only — race가 재현되면 rte_count > 0
    # 본 발견이 PHASE_C_WORKERS=4 race의 직접 증거
