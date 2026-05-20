"""ipe/catalog/__main__.py CLI 단위 테스트.

argparse 분기 + 출력 + exit code 검증.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ipe.catalog.__main__ import main
from ipe.catalog.store import promote_run
from ipe.state import ProblemState


def _make_state(title: str = "Two Sum") -> ProblemState:
    state: ProblemState = {
        "problem_title": title,
        "target_algorithm": "Two Sum",
        "target_language": "python",
        "constraints_structured": {
            "time_limit_ms": 2000,
            "memory_limit_mb": 256,
            "variables": [],
        },
        "sample_testcases": [
            {"input": str(i), "expected_output": str(i)} for i in range(3)
        ],
        "testcases": [{"id": i} for i in range(5)],
    }
    state["difficulty_label"] = "Bronze V"
    return state


def _make_run_dir(tmp_path: Path, run_id: str = "run-abc") -> Path:
    rd = tmp_path / "outputs" / run_id
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "problem.md").write_text("# Sample\nbody text", encoding="utf-8")
    (rd / "problem.json").write_text(
        json.dumps({
            "meta": {"target_algorithm": "Two Sum", "target_language": "python"},
            "problem": {"title": "Two Sum", "sample_testcases": []},
            "constraints_structured": {"time_limit_ms": 2000, "memory_limit_mb": 256},
            "difficulty": {"label": "Bronze V"},
            "testcases_inline": [],
        }),
        encoding="utf-8",
    )
    return rd


def _seed_catalog(tmp_path: Path, n: int = 1) -> tuple[Path, list[str]]:
    """n개 entry를 catalog에 미리 넣어 두고 (catalog_root, [id, ...]) 반환."""
    catalog = tmp_path / "catalog"
    ids: list[str] = []
    for i in range(n):
        rd = _make_run_dir(tmp_path, f"run-{i}")
        e = promote_run(_make_state(f"T{i}"), rd, f"run-{i}", catalog_root=catalog)
        ids.append(e["id"])
    return catalog, ids


# =============================================================================
# list
# =============================================================================


class TestListCmd:
    def test_empty_catalog(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["--catalog-root", str(tmp_path / "catalog"), "list"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "(no entries)" in out

    def test_table_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        catalog, ids = _seed_catalog(tmp_path, n=2)
        rc = main(["--catalog-root", str(catalog), "list"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "ID" in out and "STATUS" in out
        for pid in ids:
            assert pid in out

    def test_json_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        catalog, _ids = _seed_catalog(tmp_path, n=2)
        rc = main(["--catalog-root", str(catalog), "list", "--json"])
        out = capsys.readouterr().out
        assert rc == 0
        lines = [line for line in out.strip().split("\n") if line]
        assert len(lines) == 2
        for line in lines:
            json.loads(line)  # valid JSON

    def test_filter_by_status(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        catalog, ids = _seed_catalog(tmp_path, n=2)
        # 첫 번째를 approve
        main([
            "--catalog-root", str(catalog),
            "approve", ids[0],
        ])
        capsys.readouterr()  # clear

        rc = main([
            "--catalog-root", str(catalog),
            "list", "--status", "approved",
        ])
        out = capsys.readouterr().out
        assert rc == 0
        assert ids[0] in out
        assert ids[1] not in out


# =============================================================================
# show
# =============================================================================


class TestShowCmd:
    def test_show_meta_outputs_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        catalog, ids = _seed_catalog(tmp_path, n=1)
        rc = main([
            "--catalog-root", str(catalog),
            "show", ids[0], "--meta",
        ])
        out = capsys.readouterr().out
        assert rc == 0
        data = json.loads(out)
        assert data["id"] == ids[0]

    def test_show_markdown_via_symlink(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        catalog, ids = _seed_catalog(tmp_path, n=1)
        rc = main([
            "--catalog-root", str(catalog),
            "show", ids[0],
        ])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Sample" in out or "body text" in out

    def test_show_missing_id_returns_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        catalog = tmp_path / "catalog"
        rc = main([
            "--catalog-root", str(catalog),
            "show", "p_nonexistent",
        ])
        err = capsys.readouterr().err
        assert rc == 2
        assert "not found" in err


# =============================================================================
# approve / reject
# =============================================================================


class TestApproveRejectCmd:
    def test_approve_updates_entry(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        catalog, ids = _seed_catalog(tmp_path, n=1)
        rc = main([
            "--catalog-root", str(catalog),
            "approve", ids[0],
            "--by", "minsu", "--note", "ok",
        ])
        out = capsys.readouterr().out
        assert rc == 0
        assert "approved" in out
        assert "minsu" in out

    def test_reject_updates_entry(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        catalog, ids = _seed_catalog(tmp_path, n=1)
        rc = main([
            "--catalog-root", str(catalog),
            "reject", ids[0], "--note", "ambiguous",
        ])
        out = capsys.readouterr().out
        assert rc == 0
        assert "rejected" in out

    def test_approve_missing_id_returns_2(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],  # noqa: ARG002
    ) -> None:
        rc = main([
            "--catalog-root", str(tmp_path / "catalog"),
            "approve", "p_missing",
        ])
        assert rc == 2


# =============================================================================
# promote
# =============================================================================


class TestPromoteCmd:
    def test_promote_existing_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outputs = tmp_path / "outputs"
        _make_run_dir(tmp_path, "run-x")  # creates outputs/run-x with problem.json
        catalog = tmp_path / "catalog"
        rc = main([
            "--catalog-root", str(catalog),
            "promote", "run-x",
            "--outputs-root", str(outputs),
        ])
        out = capsys.readouterr().out
        assert rc == 0
        assert "promoted" in out

    def test_promote_missing_run_dir_returns_2(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],  # noqa: ARG002
    ) -> None:
        rc = main([
            "--catalog-root", str(tmp_path / "catalog"),
            "promote", "run-missing",
            "--outputs-root", str(tmp_path / "outputs"),
        ])
        assert rc == 2

    def test_promote_missing_problem_json_returns_3(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],  # noqa: ARG002
    ) -> None:
        rd = tmp_path / "outputs" / "run-broken"
        rd.mkdir(parents=True, exist_ok=True)
        # no problem.json
        rc = main([
            "--catalog-root", str(tmp_path / "catalog"),
            "promote", "run-broken",
            "--outputs-root", str(tmp_path / "outputs"),
        ])
        assert rc == 3
