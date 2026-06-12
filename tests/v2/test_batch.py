"""v2 배치 검증/문제 은행 적재 CLI 테스트 (ipe/v2/batch.py).

graph_factory 주입으로 LLM/sandbox 없이 결정론 검증 (api/main_v2 와 동일 패턴):
- seeds 파싱 (all=전체 enum / comma-sep / 미지원 값 거부)
- run 산출 파일 형상 (계약 §2.5 패키지 + batch 메타 = API job 응답과 호환)
- resume (기존 파일 skip) / --retry-failed (crash 분만 재시도)
- crash 격리 (한 run 의 예외가 배치를 못 죽임) + exit code
- --dry-run / --report-only / 비용 계산 (모델별 단가)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import ipe.v2.batch as batch_mod
from ipe.v1.schema import (
    GeneratedTestCase,
    IOContract,
    IOFieldSpec,
    IOSchema,
    ProblemBlueprint,
    ProblemSpec,
    QAFinding,
    QAReport,
    QAReview,
    SampleTestCase,
    TargetAlgorithm,
    TestSuite,
)
from ipe.v2.batch import _cost_usd, _parse_seeds, main
from ipe.v2.state import V2State, initial_v2_state

# ---------- 상태 픽스처 (test_api_server.py 와 동일 형상, 최소판) ----------


def _blueprint() -> ProblemBlueprint:
    return ProblemBlueprint(
        reduction_core=TargetAlgorithm.DIJKSTRA,
        composition=(TargetAlgorithm.UNION_FIND,),
        domain="waterworks",
        io_schema=IOSchema(
            inputs=(IOFieldSpec(name="g", type="weighted_edges"),),
            output_type="int",
            output_format="단일 정수",
        ),
    )


def _spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="상수도 배관망 점검",
        description="은닉 지문",
        io_contract=IOContract(input_format="V E\nu v w...", output_format="단일 정수"),
        sample_testcases=[
            SampleTestCase(input_text="1 0", expected_output="0"),
            SampleTestCase(input_text="2 1\n1 2 5\n1 2", expected_output="5"),
            SampleTestCase(input_text="3 2\n1 2 5\n2 3 7\n1 3", expected_output="12"),
        ],
    )


def _suite() -> TestSuite:
    return TestSuite(
        cases=(
            GeneratedTestCase(
                input_text="1 0",
                category="edge:empty",
                expected_output="0",
                golden_elapsed_ms=12,
            ),
        ),
        golden_origin="claude-opus-4-7",
    )


def _qa(passed: bool) -> QAReport:
    reviews = [
        QAReview(kind=k, passed=True) for k in ("fairness", "leakage", "difficulty")
    ]
    if passed:
        reviews.append(QAReview(kind="ambiguity", passed=True))
    else:
        reviews.append(
            QAReview(
                kind="ambiguity",
                passed=False,
                rationale="경계 미정의",
                findings=(QAFinding(severity="blocker", description="모호"),),
            )
        )
    return QAReport(reviews=tuple(reviews))


def _final_state(final_status: str) -> V2State:
    base = initial_v2_state("batch-test", TargetAlgorithm.DIJKSTRA)
    update: dict[str, object] = {"final_status": final_status, "blueprint": _blueprint()}
    if final_status in ("success", "fail_qa"):
        update.update(
            {
                "spec": _spec(),
                "test_suite": _suite(),
                "qa_report": _qa(final_status == "success"),
            }
        )
    return base.model_copy(update=update)


# ---------- mock graph factory ----------


class _CountingFactory:
    """호출 추적 graph factory — run 별 결과를 final_status 로 결정."""

    def __init__(self, final_status: str = "success") -> None:
        self.calls: list[str] = []
        self._final_status = final_status

    def __call__(self, req: Any) -> Any:
        self.calls.append(str(req.seed_algorithm))
        return _FakeGraph(_final_state(self._final_status))


class _FakeGraph:
    def __init__(self, final: V2State) -> None:
        self._final = final

    def invoke(self, state: Any, config: Any = None) -> V2State:
        return self._final


class _RaisingFactory:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, req: Any) -> Any:
        self.calls += 1
        msg = "anthropic auth error"
        raise RuntimeError(msg)


def _run(tmp_path: Path, *argv: str, factory: Any) -> int:
    return main(
        ["--out", str(tmp_path), *argv],
        graph_factory=factory,
    )


def _read(tmp_path: Path, name: str) -> dict[str, Any]:
    return json.loads((tmp_path / name).read_text())  # type: ignore[no-any-return]


# ---------- seeds 파싱 ----------


def test_parse_seeds_all_covers_full_enum() -> None:
    seeds = _parse_seeds("all")
    assert seeds == list(TargetAlgorithm)
    assert len(seeds) == len(TargetAlgorithm)


def test_parse_seeds_comma_list_and_invalid() -> None:
    assert _parse_seeds("dijkstra, bfs") == [
        TargetAlgorithm.DIJKSTRA,
        TargetAlgorithm.BFS,
    ]
    with pytest.raises(SystemExit, match="greedy"):
        _parse_seeds("dijkstra,greedy")


# ---------- run 파일 형상 (계약 §2.5 호환) ----------


def test_batch_writes_contract_package_file_and_summary(tmp_path: Path) -> None:
    factory = _CountingFactory("success")
    code = _run(
        tmp_path, "--seeds", "dijkstra", "--runs-per-seed", "1", factory=factory
    )

    assert code == 0
    assert factory.calls == ["dijkstra"]
    data = _read(tmp_path, "dijkstra_run1.json")
    assert data["status"] == "completed"
    assert data["final_status"] == "success"
    assert data["batch"]["seed"] == "dijkstra"
    assert data["batch"]["run_index"] == 1
    assert data["batch"]["mode"] == "hidden"
    assert data["composition"] == ["union_find"]
    pkg = data["package"]
    assert pkg["problem"]["title"] == "상수도 배관망 점검"
    assert pkg["meta"]["package_version"] == "1.0"
    assert pkg["meta"]["timing"]["max_golden_elapsed_ms"] == 12
    summary = _read(tmp_path, "summary.json")
    assert summary["overall"]["runs"] == 1
    assert summary["seeds"]["dijkstra"]["success"] == 1
    assert summary["seeds"]["dijkstra"]["packaged"] == 1


def test_non_packaged_fail_records_diagnostics(tmp_path: Path) -> None:
    factory = _CountingFactory("fail_verification")
    code = _run(
        tmp_path, "--seeds", "dijkstra", "--runs-per-seed", "1", factory=factory
    )

    assert code == 0  # fail_* 는 정상 측정값 — crash 만 exit 1
    data = _read(tmp_path, "dijkstra_run1.json")
    assert data["final_status"] == "fail_verification"
    assert data["package"] is None
    assert data["diagnostics"]["summary"] == "fail_verification"


# ---------- resume / retry ----------


def test_resume_skips_existing_run_file(tmp_path: Path) -> None:
    factory = _CountingFactory("success")
    (tmp_path / "dijkstra_run1.json").write_text(
        json.dumps({"batch": {"seed": "dijkstra"}, "status": "completed"})
    )

    code = _run(
        tmp_path, "--seeds", "dijkstra", "--runs-per-seed", "2", factory=factory
    )

    assert code == 0
    assert len(factory.calls) == 1  # run1 은 skip, run2 만 실행
    assert (tmp_path / "dijkstra_run2.json").exists()


def test_retry_failed_reruns_crashed_only(tmp_path: Path) -> None:
    factory = _CountingFactory("success")
    (tmp_path / "dijkstra_run1.json").write_text(
        json.dumps({"batch": {"seed": "dijkstra"}, "status": "failed", "error": "x"})
    )
    (tmp_path / "dijkstra_run2.json").write_text(
        json.dumps({"batch": {"seed": "dijkstra"}, "status": "completed"})
    )

    code = _run(
        tmp_path,
        "--seeds",
        "dijkstra",
        "--runs-per-seed",
        "2",
        "--retry-failed",
        factory=factory,
    )

    assert code == 0
    assert len(factory.calls) == 1  # crash 분(run1)만 재실행
    assert _read(tmp_path, "dijkstra_run1.json")["status"] == "completed"
    assert _read(tmp_path, "dijkstra_run2.json")["status"] == "completed"


# ---------- crash 격리 ----------


def test_crash_is_isolated_and_exits_1(tmp_path: Path) -> None:
    factory = _RaisingFactory()
    code = _run(
        tmp_path, "--seeds", "dijkstra", "--runs-per-seed", "2", factory=factory
    )

    assert code == 1  # crash 는 측정값이 아닌 결함 신호
    assert factory.calls == 2  # 첫 crash 가 두 번째 run 을 막지 않음
    data = _read(tmp_path, "dijkstra_run1.json")
    assert data["status"] == "failed"
    assert "RuntimeError" in data["error"]


# ---------- dry-run / report-only ----------


def test_dry_run_executes_nothing(tmp_path: Path) -> None:
    factory = _CountingFactory("success")
    code = _run(
        tmp_path,
        "--seeds",
        "dijkstra,bfs",
        "--runs-per-seed",
        "3",
        "--dry-run",
        factory=factory,
    )

    assert code == 0
    assert factory.calls == []
    assert list(tmp_path.glob("*.json")) == []


def test_report_only_aggregates_existing_files(tmp_path: Path) -> None:
    rows = [
        ("dijkstra_run1.json", "completed", "success", {"meta": {}}, 0.5),
        (
            "dijkstra_run2.json",
            "completed",
            "fail_qa",
            {"meta": {"qa": {"verdicts": {"leakage": False, "ambiguity": True}}}},
            0.6,
        ),
        ("bfs_run1.json", "completed", "fail_verification", None, 0.4),
        ("bfs_run2.json", "failed", None, None, None),
    ]
    for name, status, final_status, pkg, cost in rows:
        body: dict[str, Any] = {
            "batch": {"seed": name.split("_")[0], "elapsed_s": 100.0},
            "status": status,
        }
        if status == "completed":
            body.update(
                {"final_status": final_status, "package": pkg, "cost_usd": cost}
            )
        else:
            body["error"] = "RuntimeError: boom"
        (tmp_path / name).write_text(json.dumps(body))

    code = _run(tmp_path, "--report-only", factory=None)

    assert code == 0
    summary = _read(tmp_path, "summary.json")
    assert summary["overall"]["runs"] == 4
    assert summary["overall"]["crashed"] == 1
    dij = summary["seeds"]["dijkstra"]
    assert dij["runs"] == 2
    assert dij["success"] == 1
    assert dij["packaged"] == 2
    assert dij["qa_failed_kinds"] == {"leakage": 1}
    bfs = summary["seeds"]["bfs"]
    assert bfs["packaged"] == 0
    assert bfs["crashed"] == 1
    assert bfs["statuses"] == {"fail_verification": 1}


# ---------- subprocess 격리 (run 폭주가 배치를 못 죽이게) ----------


def test_single_run_mode_writes_file_and_exits_0(tmp_path: Path) -> None:
    """--single-run = 부모 배치가 스폰하는 내부 모드 — 파일 쓰고 종료."""
    factory = _CountingFactory("success")
    code = main(
        [
            "--single-run",
            "dijkstra",
            "--run-index",
            "2",
            "--run-id",
            "rid-1",
            "--out",
            str(tmp_path),
        ],
        graph_factory=factory,
    )

    assert code == 0
    data = _read(tmp_path, "dijkstra_run2.json")
    assert data["status"] == "completed"
    assert data["batch"]["run_id"] == "rid-1"
    assert data["batch"]["run_index"] == 2


def test_single_run_crash_writes_failed_and_exits_1(tmp_path: Path) -> None:
    code = main(
        ["--single-run", "dijkstra", "--run-index", "1", "--out", str(tmp_path)],
        graph_factory=_RaisingFactory(),
    )

    assert code == 1
    assert _read(tmp_path, "dijkstra_run1.json")["status"] == "failed"


def test_production_run_timeout_synthesizes_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """graph_factory 미주입(production) 경로는 subprocess — 타임아웃 시 kill 후
    failed 파일 합성 (폭주 run 이 배치/호스트를 못 죽임)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")

    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(batch_mod.subprocess, "run", fake_run)

    code = main(
        [
            "--out",
            str(tmp_path),
            "--seeds",
            "dijkstra",
            "--runs-per-seed",
            "1",
            "--run-timeout",
            "5",
        ]
    )

    assert code == 1
    data = _read(tmp_path, "dijkstra_run1.json")
    assert data["status"] == "failed"
    assert "timeout" in data["error"]


def test_production_run_no_result_file_synthesizes_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")

    class _Proc:
        returncode = 1
        stderr = "MemoryError: boom"

    captured: dict[str, Any] = {}

    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        captured["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(batch_mod.subprocess, "run", fake_run)

    code = main(
        ["--out", str(tmp_path), "--seeds", "dijkstra", "--runs-per-seed", "1"]
    )

    assert code == 1
    data = _read(tmp_path, "dijkstra_run1.json")
    assert data["status"] == "failed"
    assert "no result file" in data["error"]
    assert "MemoryError" in data["error"]
    # 자식 자기 메모리제한 플래그가 스폰 cmd 에 전파되는지 (rc=-9 증거소실 방지)
    assert "--mem-limit-gb" in captured["cmd"]


def test_apply_memory_limit_zero_is_noop() -> None:
    batch_mod._apply_memory_limit(0)  # 0=무제한 — rlimit 미접촉, 예외 없음


# ---------- 비용 계산 ----------


def test_cost_usd_applies_per_model_pricing() -> None:
    usage = {
        "claude-opus-4-7": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
        "claude-sonnet-4-6": {"input_tokens": 2_000_000, "output_tokens": 0},
        "claude-haiku-4-5": {"input_tokens": 0, "output_tokens": 1_000_000},
        "unknown-model": {"input_tokens": 9_999_999, "output_tokens": 9_999_999},
    }
    # opus 5+25=30, sonnet 2×3=6, haiku 5, unknown 은 단가 미상 → 제외
    assert _cost_usd(usage) == 41.0


def test_cost_usd_empty_usage_is_zero() -> None:
    assert _cost_usd({}) == 0.0
