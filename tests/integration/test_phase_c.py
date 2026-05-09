"""Phase C 통합 테스트 (P6.5).

generators가 채워진 상태에서 Executor가 Phase C까지 통과하는 시나리오.
generator scripts는 직접 state["generators"]에 inject (auditor와 달리
LLM mock 단계 없이 결정론적으로 검증 가능).

시나리오:
1. happy path → ``final_status='success'`` + testcases (sample + adversarial + generated)
2. broken generator script → ``last_failed_node='generator'``
3. solution RTE on generated input → ``last_failed_node='coder'``
4. slow oracle (max-stress > time_limit × 0.5) → ``last_failed_node='coder'`` (oracle slow)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ipe.nodes import executor
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.state import ProblemState

# A+B를 푸는 정해 코드
SOLVER_AB = "a, b = map(int, input().split())\nprint(a + b)\n"

# 결정론적 generator scripts (A+B 입력 형식, 1 ≤ a, b ≤ 1e9)
GEN_SMALL: dict[str, Any] = {
    "name": "gen_small",
    "category": "RANDOM_SMALL",
    "description": "small random",
    "code": (
        "import sys, random\n"
        "seed = int(sys.argv[1])\n"
        "random.seed(seed)\n"
        "a = random.randint(1, 100)\n"
        "b = random.randint(1, 100)\n"
        "print(a, b)\n"
    ),
    "seeds": [1, 2, 3],
}

GEN_LARGE: dict[str, Any] = {
    "name": "gen_large",
    "category": "MAX_STRESS",
    "description": "large values (deterministic)",
    "code": (
        "import sys\n"
        "seed = int(sys.argv[1])\n"
        "print(seed * 1000, seed * 2000)\n"
    ),
    "seeds": [1, 2],
}

GEN_BROKEN: dict[str, Any] = {
    "name": "gen_broken",
    "category": "ADVERSARIAL",
    "description": "intentionally broken",
    "code": "raise RuntimeError('broken')\n",
    "seeds": [1],
}


def _state_phase_c_ready(
    *,
    solution: str = SOLVER_AB,
    generators: list[dict[str, Any]] | None = None,
    time_limit_ms: int = 2000,
) -> ProblemState:
    """architect+coder+auditor가 채운 후의 state — Phase C 진입 준비."""
    if generators is None:
        generators = [GEN_SMALL, GEN_LARGE]
    return {
        "target_algorithm": "A+B",
        "target_language": "python",
        "problem_description": "Read two integers and print their sum.",
        "constraints": "1 <= a, b <= 1e9",
        "constraints_structured": {
            "variables": [
                {"name": "a", "min": 1, "max": 10**9, "type": "int"},
                {"name": "b", "min": 1, "max": 10**9, "type": "int"},
            ],
            "time_limit_ms": time_limit_ms,
            "memory_limit_mb": 256,
        },
        "sample_testcases": [
            {"input": "1 2\n", "expected_output": "3"},
            {"input": "10 20\n", "expected_output": "30"},
        ],
        "adversarial_inputs": [
            {"input": "1 1\n", "category": "MIN_SIZE", "reason": "smallest"},
            {"input": "5 5\n", "category": "UNIFORM", "reason": "equal"},
            {"input": "100 200\n", "category": "ADVERSARIAL", "reason": "regular"},
            {"input": "1 1000000000\n", "category": "BOUNDARY", "reason": "max b"},
            {"input": "999999999 1\n", "category": "BOUNDARY", "reason": "near max"},
            {"input": "2 3\n", "category": "MIN_SIZE", "reason": "near min"},
            {"input": "500 500\n", "category": "UNIFORM", "reason": "midrange"},
            {"input": "777 333\n", "category": "ADVERSARIAL", "reason": "regular"},
        ],
        "solution_code": solution,
        "generators": generators,
    }


# =============================================================================
# 1. Happy path — full pipeline success
# =============================================================================


def test_phase_c_happy_path_success(tmp_path: Path) -> None:
    """A+B 정해 + 8 adv + 2 gens (5 seeds total) → final_status='success'.

    testcases = 2 sample + 8 adversarial + 5 generated = 15
    """
    state = _state_phase_c_ready(generators=[GEN_SMALL, GEN_LARGE])
    final = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    assert final["final_status"] == "success", (
        f"expected success, got {final.get('final_status')} "
        f"({final.get('last_failed_node')}: {final.get('feedback_message')!r})"
    )
    assert final["last_failed_node"] is None

    testcases = final.get("testcases") or []
    sample_count = sum(1 for t in testcases if t.get("kind") == "sample")
    adv_count = sum(1 for t in testcases if t.get("kind") == "adversarial")
    gen_count = sum(1 for t in testcases if t.get("kind") == "generated")
    assert sample_count == 2
    assert adv_count == 8
    assert gen_count == 5  # GEN_SMALL × 3 seeds + GEN_LARGE × 2 seeds

    # generated testcase에는 expected_output (oracle), generator name, seed 필요
    gen_tcs = [t for t in testcases if t.get("kind") == "generated"]
    assert all("expected_output" in t for t in gen_tcs)
    assert all("generator" in t for t in gen_tcs)
    assert all("seed" in t for t in gen_tcs)

    # GEN_LARGE seed=1: print(1000, 2000) → solution → 3000
    gen_large_seed1 = next(
        t for t in gen_tcs if t["generator"] == "gen_large" and t["seed"] == 1
    )
    assert gen_large_seed1["expected_output"] == "3000"


# =============================================================================
# 2. Broken generator script → 'generator' 라우팅
# =============================================================================


def test_phase_c_broken_generator_routes_to_generator(tmp_path: Path) -> None:
    """generator script가 RuntimeError → generator failure 우세 → 'generator'."""
    state = _state_phase_c_ready(generators=[GEN_BROKEN])
    final = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    assert final.get("final_status") is None
    assert final["last_failed_node"] == "generator"
    feedback = final.get("feedback_message") or ""
    assert "generator scripts failed" in feedback


# =============================================================================
# 3. Solution RTE on generated input → 'coder'
# =============================================================================


def test_phase_c_solution_rte_routes_to_coder(tmp_path: Path) -> None:
    """솔루션이 stress 케이스에서 RTE → solution failure 우세 → 'coder'."""
    big_gen: dict[str, Any] = {
        "name": "gen_extreme",
        "category": "MAX_STRESS",
        "description": "very large",
        "code": (
            "import sys\n"
            "seed = int(sys.argv[1])\n"
            "print(seed * 100000, seed * 200000)\n"
        ),
        "seeds": [1, 2, 3],
    }
    bad_solution = (
        "a, b = map(int, input().split())\n"
        "if a > 50000:\n"
        "    raise RuntimeError('big a')\n"
        "print(a + b)\n"
    )
    state = _state_phase_c_ready(
        solution=bad_solution, generators=[GEN_SMALL, big_gen]
    )
    final = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    assert final.get("final_status") is None
    assert final["last_failed_node"] == "coder"
    feedback = final.get("feedback_message") or ""
    assert "solution failed" in feedback


# =============================================================================
# 4. Slow oracle → 'coder' (oracle slow, P6.4 50% gate)
# =============================================================================


def test_phase_c_slow_oracle_routes_to_coder(tmp_path: Path) -> None:
    """정해가 너무 느리면 'coder' 라우팅 (P6.4 50% gate).

    time_limit_ms=600 (gate=300ms), solution이 0.4s sleep — Phase A는 통과 (wall 600ms),
    하지만 stress wall_time 400ms > gate 300ms → oracle slow 시그널.
    """
    slow_solution = (
        "import time\n"
        "a, b = map(int, input().split())\n"
        "time.sleep(0.4)\n"  # 400ms — gate 300ms 초과
        "print(a + b)\n"
    )
    state = _state_phase_c_ready(
        solution=slow_solution,
        generators=[GEN_SMALL],
        time_limit_ms=600,
    )

    final = executor.run(
        state, runner=RlimitRunner(), workdir_root=tmp_path / "wd"
    )

    # 두 가능성: oracle slow ('coder') 또는 sample TLE 자체 ('coder' via Phase A 3-way)
    # 어느 쪽이든 coder 라우팅 — 그게 핵심.
    assert final["last_failed_node"] == "coder"
    feedback = final.get("feedback_message") or ""
    # P6.4 게이트가 작동하면 'oracle slow', 또는 sample/adv에서 TLE면 그쪽 메시지
    assert (
        "oracle slow" in feedback
        or "phase A failures" in feedback
        or "solution failed" in feedback
    )
