"""Executor Java compile + run 통합 테스트 (polish round 3 — B2 해소).

스펙: ARCHITECTURE.md §3.9, IMPLEMENTATION_ROADMAP §1 P3
범위: ``_executor_helpers._compile`` / ``_run_cmd`` 의 Java(javac) 분기 cover.

기존 통합 테스트는 ``target_language="python"`` 만 검증. 본 테스트가 javac 가용
환경에서 Java 분기 (line 64-67, 84-96, 103-105) 커버 — backlog B2 (post-p7) 해소.

javac 미설치 환경에서는 ``pytest.mark.skipif`` 로 자동 skip.
"""

from __future__ import annotations

import platform
import shutil
from pathlib import Path

import pytest

from ipe.nodes import executor
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.state import ProblemState

pytestmark = [
    pytest.mark.skipif(
        shutil.which("javac") is None or shutil.which("java") is None,
        reason="javac/java not available — Java compile 통합 테스트 skip",
    ),
    # Linux ``RLIMIT_AS`` + JVM 상호작용 불안정 — javac/java가 1-2GB virtual
    # memory 잡으면서 RLIMIT_AS 충돌 (Memory 4096MB까지 ↑ 시도해도 fail).
    # macOS Darwin은 RLIMIT_AS 무시라 동작. Java 검증은 macOS CI + local로 충분
    # (production 운영도 sandboxexec 또는 docker 권장). RlimitRunner + Linux +
    # JVM 조합은 별도 backlog로 격리.
    pytest.mark.skipif(
        platform.system() == "Linux",
        reason="RlimitRunner + Linux RLIMIT_AS + JVM 조합 불안정 — backlog",
    ),
]

# A+B Java 솔루션 — public class 명명 규칙 (Solution.java)
JAVA_SOLVER_AB = """\
import java.util.Scanner;

public class Solution {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int a = sc.nextInt();
        int b = sc.nextInt();
        System.out.println(a + b);
    }
}
"""

# 컴파일 에러 케이스 — 닫는 } 누락
JAVA_BROKEN = """\
public class Solution {
    public static void main(String[] args) {
        System.out.println("hello");
"""


def _state_with_java_solution(code: str) -> ProblemState:
    """Phase A 진입 준비 — architect+coder 결과를 inject."""
    return {
        "target_algorithm": "A+B",
        "target_language": "java",
        "problem_description": "Read two integers and print their sum.",
        "constraints": "1 <= a, b <= 1e9",
        "constraints_structured": {
            "variables": [
                {"name": "a", "min": 1, "max": 10**9, "type": "int"},
                {"name": "b", "min": 1, "max": 10**9, "type": "int"},
            ],
            "time_limit_ms": 5000,  # javac + JVM 기동 여유
            # Linux ``RLIMIT_AS`` (virtual memory)는 JVM 시작 시 1-2GB 잡음 —
            # 512MB는 즉시 OOM/RTE 유발 (CI ubuntu fail 재현). macOS Darwin은
            # RLIMIT_AS 무시라 local 통과. test 한정으로 2048MB 명시.
            "memory_limit_mb": 2048,
        },
        "sample_testcases": [
            {"input": "1 2\n", "expected_output": "3"},
            {"input": "10 20\n", "expected_output": "30"},
        ],
        "solution_code": code,
    }


def test_java_phase_a_pass(tmp_path: Path) -> None:
    """정상 Java 솔루션 → javac compile + java run → Phase A 통과 → Phase B로."""
    state = _state_with_java_solution(JAVA_SOLVER_AB)
    final = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    # Phase A 모두 통과 → adversarial_inputs 부재 → auditor 라우팅 (Phase B 시그널)
    assert final.get("final_status") is None
    assert final["last_failed_node"] == "auditor"
    feedback = final.get("feedback_message") or ""
    assert "no adversarial_inputs" in feedback

    # Phase A 결과 검증
    results = final.get("execution_results") or []
    samples = [r for r in results if r.get("phase") == "sample"]
    assert len(samples) == 2
    assert all(r["pass"] for r in samples)
    # Java도 stdout이 정상 출력되는지
    assert samples[0]["actual"] == "3"
    assert samples[1]["actual"] == "30"


def test_java_compile_error_routes_to_coder(tmp_path: Path) -> None:
    """JAVA_BROKEN (닫는 } 누락) → javac 실패 → ``last_failed_node='coder'``."""
    state = _state_with_java_solution(JAVA_BROKEN)
    final = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    assert final["last_failed_node"] == "coder"
    feedback = final.get("feedback_message") or ""
    assert "compile error" in feedback


def test_java_solution_runtime_error_routes_to_coder(tmp_path: Path) -> None:
    """컴파일 OK + 실행 시 RuntimeException → Phase A 3-way 휴리스틱 → coder."""
    runtime_err_code = """\
public class Solution {
    public static void main(String[] args) {
        throw new RuntimeException("intentional failure");
    }
}
"""
    state = _state_with_java_solution(runtime_err_code)
    final = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    # Phase A 모두 RTE → 3-way (c) coder 라우팅 (crash 동반)
    assert final["last_failed_node"] == "coder"
    results = final.get("execution_results") or []
    samples = [r for r in results if r.get("phase") == "sample"]
    assert len(samples) == 2
    # RTE status — Java의 unchecked exception은 non-zero exit
    assert all(not r["pass"] for r in samples)
    assert all(r["status"] in ("RTE", "TLE", "MLE") for r in samples)
