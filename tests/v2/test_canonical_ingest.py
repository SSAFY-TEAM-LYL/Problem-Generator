"""canonical(v1) → v2 DB 적재 브리지 테스트.

v1 canonical 그래프의 최종 V1State 를 v2 persist_run body 로 변환하고, sqlite
round-trip 으로 problems/test_cases 에 실제 적재되는지(=DB 스키마 호환) 검증한다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select

from ipe.v1.schema import (
    IOContract,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    TargetAlgorithm,
)
from ipe.v1.state import V1State, initial_state
from ipe.v2.canonical_ingest import canonical_body
from ipe.v2.db import init_schema, persist_run
from ipe.v2.db.schema import problems, test_cases


def _success_state() -> V1State:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="두 거래 합 매칭",
        description="합이 target 인 서로 다른 두 수의 쌍 개수를 센다.",
        io_contract=IOContract(
            input_format="N\\na_1..a_N\\ntarget", output_format="개수"
        ),
        sample_testcases=[
            SampleTestCase(input_text="3\\n1 2 3\\n5", expected_output="1"),
            SampleTestCase(input_text="2\\n1 1\\n2", expected_output="1"),
            SampleTestCase(input_text="1\\n5\\n5", expected_output="0"),
        ],
    )
    attempt = SolutionAttempt(code="print(0)", iteration=0)
    return initial_state("r1", TargetAlgorithm.TWO_SUM).model_copy(
        update={"spec": spec, "attempt": attempt, "final_status": "success"}
    )


def test_canonical_body_shape() -> None:
    body = canonical_body(_success_state(), run_id="canon-1", seed="two_sum")
    assert body["final_status"] == "success"
    assert body["batch"] == {"run_id": "canon-1", "seed": "two_sum", "mode": "canonical"}
    pkg = body["package"]
    assert pkg["problem"]["title"] == "두 거래 합 매칭"
    assert pkg["problem"]["description"]
    assert pkg["problem"]["io_contract"]["input_format"]
    assert pkg["problem"]["io_contract"]["output_format"]
    assert pkg["solution"]["golden_code"] == "print(0)"
    assert pkg["solution"]["language"] == "python"
    assert pkg["meta"]["hidden_algorithm"] == "two_sum"
    assert pkg["meta"]["composition"] == []  # canonical = 무합성 (쉬운 문제 핵심)
    assert pkg["meta"]["mode"] == "canonical"
    # canonical 은 풀 채점셋 노드 없음 → sample(3) 을 test_suite case 로 사용
    assert len(pkg["test_suite"]["cases"]) == 3
    assert pkg["test_suite"]["cases"][0]["category"] == "sample"


def test_canonical_body_persists_to_v2_db() -> None:
    """round-trip: canonical body → persist_run → problems+test_cases 적재(스키마 호환)."""
    body = canonical_body(_success_state(), run_id="canon-rt", seed="two_sum")
    engine = create_engine("sqlite://")
    init_schema(engine)
    pid = persist_run(engine, body)
    assert pid is not None
    with engine.connect() as c:
        prob = c.execute(select(problems).where(problems.c.id == pid)).mappings().one()
        assert prob["title"] == "두 거래 합 매칭"
        assert prob["algorithm"] == "two_sum"
        assert prob["solution_code"] == "print(0)"
        assert prob["solution_language"] == "python"
        assert prob["status"] == "draft"
        cases = c.execute(
            select(test_cases).where(test_cases.c.problem_id == pid)
        ).all()
        assert len(cases) == 3  # samples → test_cases


def test_canonical_body_rejects_incomplete() -> None:
    """spec/attempt 없는 미완 run 은 변환 거부 (success 만 적재)."""
    incomplete = initial_state("r1", TargetAlgorithm.TWO_SUM)  # spec/attempt = None
    with pytest.raises(ValueError):
        canonical_body(incomplete, run_id="x", seed="two_sum")


def test_canonical_body_uses_provided_full_suite() -> None:
    """test_suite 오버라이드 → body 채점셋이 sample 이 아닌 풀셋 (timing=golden_elapsed)."""
    from ipe.v1.schema import GeneratedTestCase, TestSuite

    full = TestSuite(
        cases=(
            GeneratedTestCase(
                input_text="3\\n1 2 3\\n5",
                expected_output="1",
                category="sample",
                golden_elapsed_ms=4,
            ),
            GeneratedTestCase(
                input_text="6\\n9 8 7 6 5 4\\n13",
                expected_output="2",
                category="large",
                golden_elapsed_ms=40,
            ),
        ),
        golden_origin="opus",
    )
    body = canonical_body(
        _success_state(), run_id="canon-fs", seed="two_sum", test_suite=full
    )
    suite = body["package"]["test_suite"]
    assert len(suite["cases"]) == 2  # sample 3 이 아니라 제공된 풀셋 2
    assert {c["category"] for c in suite["cases"]} == {"sample", "large"}
    assert suite["origin"] == "opus"  # golden_origin → origin (provenance)
    # timing 은 assembled 케이스의 golden_elapsed_ms 최대값 (백엔드 TL 산정 근거)
    assert body["package"]["meta"]["timing"]["max_golden_elapsed_ms"] == 40


def test_canonical_body_defaults_to_samples_without_override() -> None:
    """test_suite 없으면 기존 동작 — sample 을 채점셋으로 (canonical_samples origin)."""
    body = canonical_body(_success_state(), run_id="canon-d", seed="two_sum")
    suite = body["package"]["test_suite"]
    assert suite["origin"] == "canonical_samples"
    assert {c["category"] for c in suite["cases"]} == {"sample"}
