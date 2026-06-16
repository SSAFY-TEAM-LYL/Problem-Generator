"""문제 은행 관리 콘솔(admin) 단위테스트 — sqlite + TestClient (PG 불요).

포터블 스키마(JSON variant) 로 sqlite 에서 CRUD 엔드포인트를 그대로 검증한다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.engine import Engine

from ipe.v2.admin import create_admin_app
from ipe.v2.db import init_schema, problems, test_cases

_PID = "11111111-1111-1111-1111-111111111111"


def _engine(tmp_path: Path) -> Engine:
    eng = create_engine(f"sqlite:///{tmp_path / 'bank.db'}")
    init_schema(eng)
    return eng


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(problems).values(
                id=_PID,
                title="다익스트라 최단경로",
                description="설명",
                input_format="V E",
                output_format="int",
                constraints=[{"name": "V", "min_value": 1, "max_value": 1000}],
                samples=[{"input_text": "2 1", "expected_output": "5"}],
                internal_meta={"hidden_algorithm": "dijkstra"},
                solution_code="print(5)",
                solution_language="python",
                status="draft",
                time_limit_ms=3000,
                created_at=datetime.now(UTC),
            )
        )
        conn.execute(
            insert(test_cases),
            [
                {"problem_id": _PID, "seq": 0, "input": "2 1", "expected": "5",
                 "category": "sample"},
                {"problem_id": _PID, "seq": 1, "input": "3 0", "expected": "-1",
                 "category": "edge"},
            ],
        )


def _client(tmp_path: Path) -> TestClient:
    engine = _engine(tmp_path)
    _seed(engine)
    return TestClient(create_admin_app(engine))


def test_stats_counts(tmp_path: Path) -> None:
    s = _client(tmp_path).get("/api/stats").json()
    assert s["total"] == 1
    assert s["test_cases"] == 2
    assert s["by_status"] == {"draft": 1}


def test_list_exposes_seed_and_case_count(tmp_path: Path) -> None:
    rows = _client(tmp_path).get("/api/problems").json()
    assert len(rows) == 1
    assert rows[0]["seed"] == "dijkstra"
    assert rows[0]["test_case_count"] == 2


def test_search_matches_title_or_seed(tmp_path: Path) -> None:
    cl = _client(tmp_path)
    assert len(cl.get("/api/problems?q=dijkstra").json()) == 1
    assert len(cl.get("/api/problems?q=다익스트라").json()) == 1
    assert len(cl.get("/api/problems?q=없는키워드").json()) == 0


def test_filter_by_status(tmp_path: Path) -> None:
    cl = _client(tmp_path)
    assert len(cl.get("/api/problems?status=draft").json()) == 1
    assert len(cl.get("/api/problems?status=published").json()) == 0


def test_detail_includes_ordered_cases(tmp_path: Path) -> None:
    d = _client(tmp_path).get(f"/api/problems/{_PID}").json()
    assert d["title"] == "다익스트라 최단경로"
    assert [c["seq"] for c in d["test_cases"]] == [0, 1]


def test_update_problem_fields(tmp_path: Path) -> None:
    cl = _client(tmp_path)
    out = cl.put(
        f"/api/problems/{_PID}",
        json={"status": "published", "title": "수정", "time_limit_ms": 5000},
    ).json()
    assert out["status"] == "published"
    assert out["title"] == "수정"
    assert out["time_limit_ms"] == 5000


def test_update_rejects_invalid_status(tmp_path: Path) -> None:
    r = _client(tmp_path).put(f"/api/problems/{_PID}", json={"status": "bogus"})
    assert r.status_code == 400


def test_update_rejects_empty_payload(tmp_path: Path) -> None:
    r = _client(tmp_path).put(f"/api/problems/{_PID}", json={"not_a_field": 1})
    assert r.status_code == 400


def test_delete_problem_cascades_cases(tmp_path: Path) -> None:
    cl = _client(tmp_path)
    assert cl.delete(f"/api/problems/{_PID}").status_code == 200
    assert cl.get("/api/stats").json()["total"] == 0
    assert cl.get("/api/stats").json()["test_cases"] == 0


def test_update_test_case(tmp_path: Path) -> None:
    cl = _client(tmp_path)
    cid = cl.get(f"/api/problems/{_PID}").json()["test_cases"][0]["id"]
    out = cl.put(f"/api/test_cases/{cid}", json={"expected": "999"}).json()
    assert out["expected"] == "999"


def test_add_test_case_appends_seq(tmp_path: Path) -> None:
    cl = _client(tmp_path)
    r = cl.post(f"/api/problems/{_PID}/test_cases", json={"input": "x", "expected": "y"})
    assert r.status_code == 201
    assert r.json()["seq"] == 2


def test_delete_test_case(tmp_path: Path) -> None:
    cl = _client(tmp_path)
    cid = cl.get(f"/api/problems/{_PID}").json()["test_cases"][0]["id"]
    assert cl.delete(f"/api/test_cases/{cid}").status_code == 200
    assert len(cl.get(f"/api/problems/{_PID}").json()["test_cases"]) == 1


def test_missing_problem_returns_404(tmp_path: Path) -> None:
    cl = _client(tmp_path)
    assert cl.get("/api/problems/nope").status_code == 404
    assert cl.delete("/api/problems/nope").status_code == 404


def test_index_serves_html(tmp_path: Path) -> None:
    body = _client(tmp_path).get("/").text
    assert "<title>IPE 문제 은행 관리</title>" in body
