"""ipe/catalog/store.py 단위 테스트.

스펙: docs/catalog/SCHEMA.md (이 PR에서 작성), ipe/catalog/store.py
범위: promote_run / list_entries / find / set_status / idempotency / symlink.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ipe.catalog.store import (
    _problem_id,
    find,
    list_entries,
    promote_run,
    set_status,
)
from ipe.state import ProblemState


def _make_run_dir(tmp_path: Path, run_id: str = "run-abc") -> Path:
    """Mock outputs/<run_id>/ — problem.md placeholder + 디렉토리만."""
    rd = tmp_path / "outputs" / run_id
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "problem.md").write_text("# Mock Problem\nbody", encoding="utf-8")
    (rd / "problem.json").write_text("{}", encoding="utf-8")
    return rd


def _make_state(title: str = "Two Sum", algorithm: str = "Two Sum") -> ProblemState:
    state: ProblemState = {
        "problem_title": title,
        "target_algorithm": algorithm,
        "target_language": "python",
        "constraints_structured": {
            "time_limit_ms": 2000,
            "memory_limit_mb": 256,
            "variables": [],
        },
        "sample_testcases": [
            {"input": "1", "expected_output": "1"},
            {"input": "2", "expected_output": "2"},
            {"input": "3", "expected_output": "3"},
        ],
        "testcases": [{"id": i} for i in range(10)],
    }
    state["difficulty_label"] = "Silver V"
    return state


# =============================================================================
# _problem_id — deterministic hash
# =============================================================================


class TestProblemId:
    def test_same_inputs_same_id(self) -> None:
        assert _problem_id("run-1", "Two Sum") == _problem_id("run-1", "Two Sum")

    def test_different_run_id_different_id(self) -> None:
        assert _problem_id("run-1", "X") != _problem_id("run-2", "X")

    def test_different_title_different_id(self) -> None:
        assert _problem_id("run-1", "A") != _problem_id("run-1", "B")

    def test_id_format(self) -> None:
        pid = _problem_id("any-run", "any-title")
        assert pid.startswith("p_")
        assert len(pid) == 14  # "p_" + 12 hex
        assert all(c in "0123456789abcdef" for c in pid[2:])


# =============================================================================
# promote_run — JSONL + symlink + idempotency
# =============================================================================


class TestPromoteRun:
    def test_writes_jsonl_row(self, tmp_path: Path) -> None:
        catalog = tmp_path / "catalog"
        run_dir = _make_run_dir(tmp_path)
        state = _make_state(title="Two Sum")

        entry = promote_run(state, run_dir, "run-abc", catalog_root=catalog)

        assert entry["run_id"] == "run-abc"
        assert entry["title"] == "Two Sum"
        assert entry["algorithm"] == "Two Sum"
        assert entry["status"] == "draft"
        assert entry["time_limit_ms"] == 2000
        assert entry["memory_limit_mb"] == 256
        assert entry["sample_count"] == 3
        assert entry["testcase_count"] == 10
        assert entry["difficulty_label"] == "Silver V"
        assert entry["id"].startswith("p_")
        # created_at: ISO-8601 UTC w/ Z
        assert (entry.get("created_at") or "").endswith("Z")

        # JSONL 파일에 1 row 기록됨
        jsonl = (catalog / "problems.jsonl").read_text(encoding="utf-8")
        rows = [json.loads(line) for line in jsonl.strip().split("\n")]
        assert len(rows) == 1
        assert rows[0]["id"] == entry["id"]

    def test_creates_symlink(self, tmp_path: Path) -> None:
        catalog = tmp_path / "outputs" / "catalog"
        run_dir = _make_run_dir(tmp_path)
        state = _make_state()

        entry = promote_run(state, run_dir, "run-abc", catalog_root=catalog)
        link = catalog / "problems" / entry["id"]

        assert link.is_symlink() or link.exists()
        # symlink target은 run_dir과 같은 콘텐츠 (problem.md 읽기 가능)
        assert (link / "problem.md").read_text(encoding="utf-8").startswith("# Mock")

    def test_idempotent_same_run(self, tmp_path: Path) -> None:
        """같은 run_id를 두 번 promote → 1 row만 (기존 entry 반환)."""
        catalog = tmp_path / "catalog"
        run_dir = _make_run_dir(tmp_path)
        state = _make_state()

        e1 = promote_run(state, run_dir, "run-abc", catalog_root=catalog)
        e2 = promote_run(state, run_dir, "run-abc", catalog_root=catalog)

        assert e1["id"] == e2["id"]
        entries = list_entries(catalog_root=catalog)
        assert len(entries) == 1

    def test_different_runs_different_rows(self, tmp_path: Path) -> None:
        catalog = tmp_path / "catalog"
        rd_a = _make_run_dir(tmp_path, "run-a")
        rd_b = _make_run_dir(tmp_path, "run-b")
        state = _make_state()

        promote_run(state, rd_a, "run-a", catalog_root=catalog)
        promote_run(state, rd_b, "run-b", catalog_root=catalog)

        entries = list_entries(catalog_root=catalog)
        assert len(entries) == 2
        assert {e["run_id"] for e in entries} == {"run-a", "run-b"}

    def test_idempotent_preserves_status(self, tmp_path: Path) -> None:
        """이미 approved 상태인 entry는 re-promote 후에도 status 보존."""
        catalog = tmp_path / "catalog"
        run_dir = _make_run_dir(tmp_path)
        state = _make_state()

        e1 = promote_run(state, run_dir, "run-abc", catalog_root=catalog)
        set_status(e1["id"], "approved", by="reviewer", catalog_root=catalog)
        e2 = promote_run(state, run_dir, "run-abc", catalog_root=catalog)

        assert e2["status"] == "approved"


# =============================================================================
# list_entries
# =============================================================================


class TestListEntries:
    def test_empty_catalog_returns_empty(self, tmp_path: Path) -> None:
        assert list_entries(catalog_root=tmp_path / "catalog") == []

    def test_filter_by_status(self, tmp_path: Path) -> None:
        catalog = tmp_path / "catalog"
        for i in range(3):
            promote_run(
                _make_state(title=f"T{i}"),
                _make_run_dir(tmp_path, f"run-{i}"),
                f"run-{i}",
                catalog_root=catalog,
            )
        entries = list_entries(catalog_root=catalog)
        set_status(entries[0]["id"], "approved", catalog_root=catalog)
        set_status(entries[1]["id"], "rejected", catalog_root=catalog)

        assert len(list_entries(status="draft", catalog_root=catalog)) == 1
        assert len(list_entries(status="approved", catalog_root=catalog)) == 1
        assert len(list_entries(status="rejected", catalog_root=catalog)) == 1
        assert len(list_entries(catalog_root=catalog)) == 3

    def test_invalid_status_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid status"):
            list_entries(status="banana", catalog_root=tmp_path)  # type: ignore[arg-type]


# =============================================================================
# find
# =============================================================================


class TestFind:
    def test_returns_entry_when_present(self, tmp_path: Path) -> None:
        catalog = tmp_path / "catalog"
        e = promote_run(
            _make_state(), _make_run_dir(tmp_path), "run-abc",
            catalog_root=catalog,
        )
        found = find(e["id"], catalog_root=catalog)
        assert found is not None
        assert found["id"] == e["id"]

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert find("p_nonexistent", catalog_root=tmp_path / "catalog") is None


# =============================================================================
# set_status — review workflow
# =============================================================================


class TestSetStatus:
    def test_approve_updates_fields(self, tmp_path: Path) -> None:
        catalog = tmp_path / "catalog"
        e = promote_run(
            _make_state(), _make_run_dir(tmp_path), "run-abc",
            catalog_root=catalog,
        )
        updated = set_status(
            e["id"], "approved",
            by="reviewer-1", note="looks good",
            catalog_root=catalog,
        )
        assert updated["status"] == "approved"
        assert updated["reviewed_by"] == "reviewer-1"
        assert updated["review_note"] == "looks good"
        assert (updated.get("reviewed_at") or "").endswith("Z")

    def test_reject_updates_fields(self, tmp_path: Path) -> None:
        catalog = tmp_path / "catalog"
        e = promote_run(
            _make_state(), _make_run_dir(tmp_path), "run-abc",
            catalog_root=catalog,
        )
        updated = set_status(
            e["id"], "rejected",
            note="ambiguous statement",
            catalog_root=catalog,
        )
        assert updated["status"] == "rejected"
        assert updated["review_note"] == "ambiguous statement"

    def test_missing_id_raises(self, tmp_path: Path) -> None:
        with pytest.raises(KeyError, match="not found"):
            set_status(
                "p_missing", "approved",
                catalog_root=tmp_path / "catalog",
            )

    def test_invalid_status_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid status"):
            set_status(
                "p_x", "weird",  # type: ignore[arg-type]
                catalog_root=tmp_path / "catalog",
            )

    def test_status_change_does_not_mutate_other_entries(self, tmp_path: Path) -> None:
        catalog = tmp_path / "catalog"
        e1 = promote_run(
            _make_state("T1"), _make_run_dir(tmp_path, "r1"), "r1",
            catalog_root=catalog,
        )
        e2 = promote_run(
            _make_state("T2"), _make_run_dir(tmp_path, "r2"), "r2",
            catalog_root=catalog,
        )
        set_status(e1["id"], "approved", catalog_root=catalog)
        e2_after = find(e2["id"], catalog_root=catalog)
        assert e2_after is not None
        assert e2_after["status"] == "draft"  # 영향 없음


# =============================================================================
# save_result integration — promote_to_catalog kwarg
# =============================================================================


class TestSaveResultIntegration:
    def test_save_result_skips_catalog_when_flag_off(self, tmp_path: Path) -> None:
        from ipe.io import save_result
        state: ProblemState = {
            **_make_state(),
            "final_status": "success",
        }
        run_dir = _make_run_dir(tmp_path)
        catalog = tmp_path / "catalog"
        # default promote_to_catalog=False → catalog 안 만들어짐
        save_result(
            state, run_dir,
            by_name_root=tmp_path / "by-name",
        )
        assert not (catalog / "problems.jsonl").exists()

    def test_save_result_promotes_when_flag_on_and_success(
        self, tmp_path: Path
    ) -> None:
        from ipe.io import save_result
        state: ProblemState = {
            **_make_state(),
            "final_status": "success",
        }
        run_dir = _make_run_dir(tmp_path)
        catalog = tmp_path / "catalog"
        save_result(
            state, run_dir,
            by_name_root=tmp_path / "by-name",
            promote_to_catalog=True,
            catalog_root=catalog,
        )
        entries = list_entries(catalog_root=catalog)
        assert len(entries) == 1
        assert entries[0]["status"] == "draft"

    def test_save_result_skips_catalog_when_not_success(
        self, tmp_path: Path
    ) -> None:
        """budget_exhausted / max_iterations 등 실패는 promote 안 함."""
        from ipe.io import save_result
        state: ProblemState = {
            **_make_state(),
            "final_status": "budget_exhausted",
        }
        run_dir = _make_run_dir(tmp_path)
        catalog = tmp_path / "catalog"
        save_result(
            state, run_dir,
            by_name_root=tmp_path / "by-name",
            promote_to_catalog=True,
            catalog_root=catalog,
        )
        # JSONL 없음 (failed run은 promote skip)
        assert not (catalog / "problems.jsonl").exists()
