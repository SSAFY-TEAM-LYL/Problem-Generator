"""Output Persistence 통합 테스트 (P10.4).

스펙: PROJECT_SPEC.md §6, IMPLEMENTATION_ROADMAP §1 P10.4
범위: full graph cycle → save_result 호출 → 모든 산출물 파일 + symlink 검증.

mock helpers는 ``tests/integration/_helpers.py`` (P8 audit C1) 사용.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ipe.graph import build_graph
from ipe.io import _create_by_name_symlink, save_result
from ipe.observability import LLMCallTracker
from ipe.sandbox.rlimit_runner import RlimitRunner
from tests.integration._helpers import (
    initial_state,
    wire_all_chats_normal,
)


def test_save_result_full_cycle_creates_all_outputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """happy path → save_result → SPEC §6 산출물 모두 생성."""
    wire_all_chats_normal(monkeypatch)

    run_dir = tmp_path / "run_xyz"
    by_name = tmp_path / "by-name"
    runner = RlimitRunner()
    tracker = LLMCallTracker("run_xyz", run_dir / "llm_traces")
    graph = build_graph(tracker=tracker, runner=runner, workdir_root=tmp_path / "wd")

    final = graph.invoke(initial_state())
    assert final.get("final_status") == "success"

    save_result(final, run_dir, by_name_root=by_name)

    # ── 1. 핵심 파일 존재
    assert (run_dir / "problem.json").exists()
    assert (run_dir / "problem.md").exists()
    assert (run_dir / "solution.py").exists()

    # ── 2. solution.py 내용 = state.solution_code
    code = (run_dir / "solution.py").read_text(encoding="utf-8")
    assert "input().split()" in code

    # ── 3. generators/<name>.py 존재 (Phase C 통과 시)
    gen_dir = run_dir / "generators"
    assert gen_dir.is_dir()
    gen_files = list(gen_dir.glob("*.py"))
    assert len(gen_files) >= 3  # GEN_RESPONSE 3개

    # ── 4. tests/<NN>.in/.out + manifest.json
    tests_dir = run_dir / "tests"
    assert tests_dir.is_dir()
    in_files = sorted(tests_dir.glob("*.in"))
    out_files = sorted(tests_dir.glob("*.out"))
    assert len(in_files) == len(out_files)
    assert len(in_files) >= 1  # 최소 sample 1개
    # 1-indexed zero-padded
    assert in_files[0].name == "01.in"

    manifest_path = tests_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(manifest, list)
    assert len(manifest) == len(in_files)
    assert manifest[0]["index"] == 1
    assert manifest[0]["filename"] == "01"

    # ── 5. problem.json schema (SPEC §6 핵심 필드)
    problem = json.loads((run_dir / "problem.json").read_text(encoding="utf-8"))
    assert "meta" in problem
    assert problem["meta"]["target_algorithm"] == "A+B"
    assert problem["meta"]["final_status"] == "success"
    assert "constraints_structured" in problem
    assert "problem" in problem
    assert "solution" in problem
    assert problem["solution"]["language"] == "python"
    assert "generators" in problem
    assert "testcase_manifest" in problem
    assert "execution_results" in problem
    assert "llm_calls" in problem

    # P9 difficulty 블록 (success 후 evaluator 통과)
    assert "difficulty" in problem
    assert problem["difficulty"]["label"] == "Bronze V"
    assert "bj_1000_bronze5" in problem["difficulty"]["calibration_anchors"]

    # llm_call_summary
    summary = problem["meta"]["llm_call_summary"]
    assert summary["total_calls"] >= 4  # architect/coder/auditor/generator/evaluator
    assert summary["by_node"].get("architect", 0) >= 1
    assert summary["by_node"].get("evaluator", 0) >= 1

    # ── 6. by-name symlink → run_id
    symlinks = list(by_name.iterdir())
    assert len(symlinks) == 1
    link = symlinks[0]
    assert link.is_symlink()
    # symlink target은 ../<run_id_dir_name>
    target = link.readlink()
    assert target.name == run_dir.name


def test_save_result_skips_existing_symlink(tmp_path: Path) -> None:
    """by-name 이름이 이미 있으면 symlink 충돌 회피 (skip, 예외 없음)."""
    run_dir = tmp_path / "run_a"
    run_dir.mkdir()
    by_name = tmp_path / "by-name"
    by_name.mkdir()

    # 1번째 symlink 생성
    link1 = _create_by_name_symlink(
        run_dir, algorithm="X", timestamp="20260509_120000",
        by_name_root=by_name,
    )
    assert link1 is not None
    assert link1.is_symlink()

    # 같은 (timestamp, algo) → skip
    link2 = _create_by_name_symlink(
        run_dir, algorithm="X", timestamp="20260509_120000",
        by_name_root=by_name,
    )
    assert link2 is None  # 충돌 시 None 반환
