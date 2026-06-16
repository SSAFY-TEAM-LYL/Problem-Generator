"""DB 문제 은행 관리 콘솔 — 단일 페이지 master-detail CRUD (내부 운영 전용).

``problems`` (+ ``test_cases``) 에 대한 목록·검색·조회·수정·상태변경·삭제 + 케이스 편집.
생성 파이프라인(``api.py``)과 **격리된 독립 FastAPI 앱** — 운영 생성 API 를 오염시키지
않는다. DB 는 ``--db-url`` 로 주입(예: ``postgresql+psycopg://fly-user:pw@127.0.0.1:16380/
fly-db``, fly proxy 경유). 비밀번호는 소스에 두지 않는다(보안 §secret).

기동::

    python -m ipe.v2.admin \
        --db-url "postgresql+psycopg://USER:PW@127.0.0.1:16380/fly-db" --port 8800
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Engine

from .db.schema import problems, test_cases

_PAGE = Path(__file__).with_name("admin_page.html")

# 응시자 비노출/내부 필드 포함 — 관리자는 전부 볼 수 있어야 함(내부 툴).
_PROBLEM_EDITABLE: frozenset[str] = frozenset(
    {
        "title",
        "description",
        "input_format",
        "output_format",
        "constraints",
        "samples",
        "internal_meta",
        "solution_code",
        "solution_language",
        "status",
        "time_limit_ms",
    }
)
_STATUSES: frozenset[str] = frozenset({"draft", "review", "published"})
_CASE_EDITABLE: frozenset[str] = frozenset({"input", "expected", "category", "seq"})


def _jsonable(value: Any) -> Any:
    """created_at(datetime) 등 비-JSON 값을 직렬화 가능 형태로."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _problem_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in row.items()}


def _seed_of(internal_meta: Any) -> str | None:
    """list 표시용 시드 식별 — internal_meta.hidden_algorithm (계약 §2.5)."""
    if isinstance(internal_meta, dict):
        val = internal_meta.get("hidden_algorithm") or internal_meta.get("seed")
        return str(val) if val is not None else None
    return None


def create_admin_app(engine: Engine) -> FastAPI:
    """문제 은행 관리 FastAPI 앱 — ``engine`` 은 호출자가 주입(테스트=sqlite, 운영=PG)."""
    app = FastAPI(title="IPE 문제 은행 관리", version="1.0")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _PAGE.read_text(encoding="utf-8")

    @app.get("/api/stats")
    def stats() -> dict[str, Any]:
        with engine.connect() as conn:
            status_rows = conn.execute(
                select(problems.c.status, func.count()).group_by(problems.c.status)
            ).all()
            total = int(
                conn.execute(select(func.count()).select_from(problems)).scalar() or 0
            )
            cases = int(
                conn.execute(select(func.count()).select_from(test_cases)).scalar() or 0
            )
        return {
            "total": total,
            "test_cases": cases,
            "by_status": {str(r[0]): int(r[1]) for r in status_rows},
        }

    @app.get("/api/problems")
    def list_problems(
        status: str | None = None, q: str | None = None
    ) -> list[dict[str, Any]]:
        with engine.connect() as conn:
            counts = {
                pid: int(n)
                for pid, n in conn.execute(
                    select(test_cases.c.problem_id, func.count()).group_by(
                        test_cases.c.problem_id
                    )
                ).all()
            }
            stmt = select(
                problems.c.id,
                problems.c.title,
                problems.c.status,
                problems.c.internal_meta,
                problems.c.time_limit_ms,
                problems.c.created_at,
            ).order_by(problems.c.created_at.desc())
            if status:
                stmt = stmt.where(problems.c.status == status)
            rows = conn.execute(stmt).mappings().all()
        out: list[dict[str, Any]] = []
        needle = (q or "").lower().strip()
        for r in rows:
            seed = _seed_of(r["internal_meta"])
            title = r["title"] or ""
            if (
                needle
                and needle not in title.lower()
                and needle not in (seed or "").lower()
            ):
                continue
            out.append(
                {
                    "id": r["id"],
                    "title": title,
                    "status": r["status"],
                    "seed": seed,
                    "time_limit_ms": r["time_limit_ms"],
                    "created_at": _jsonable(r["created_at"]),
                    "test_case_count": counts.get(r["id"], 0),
                }
            )
        return out

    @app.get("/api/problems/{pid}")
    def get_problem(pid: str) -> dict[str, Any]:
        with engine.connect() as conn:
            row = (
                conn.execute(select(problems).where(problems.c.id == pid))
                .mappings()
                .first()
            )
            if row is None:
                raise HTTPException(status_code=404, detail="problem not found")
            cases = (
                conn.execute(
                    select(test_cases)
                    .where(test_cases.c.problem_id == pid)
                    .order_by(test_cases.c.seq)
                )
                .mappings()
                .all()
            )
        result = _problem_row(dict(row))
        result["test_cases"] = [dict(c) for c in cases]
        return result

    @app.put("/api/problems/{pid}")
    def update_problem(
        pid: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        values = {k: v for k, v in payload.items() if k in _PROBLEM_EDITABLE}
        if not values:
            raise HTTPException(status_code=400, detail="no editable field in payload")
        if "status" in values and values["status"] not in _STATUSES:
            raise HTTPException(
                status_code=400, detail=f"status must be one of {sorted(_STATUSES)}"
            )
        with engine.begin() as conn:
            res = conn.execute(
                update(problems).where(problems.c.id == pid).values(**values)
            )
            if res.rowcount == 0:
                raise HTTPException(status_code=404, detail="problem not found")
            row = (
                conn.execute(select(problems).where(problems.c.id == pid))
                .mappings()
                .first()
            )
        assert row is not None
        return _problem_row(dict(row))

    @app.delete("/api/problems/{pid}")
    def delete_problem(pid: str) -> dict[str, Any]:
        # 자식(test_cases) 먼저 명시 삭제 — DB FK CASCADE 에 의존하지 않음
        # (sqlite 는 기본 FK 미적용). 운영 PG 에서도 동일·안전.
        with engine.begin() as conn:
            exists = conn.execute(
                select(problems.c.id).where(problems.c.id == pid)
            ).first()
            if exists is None:
                raise HTTPException(status_code=404, detail="problem not found")
            conn.execute(delete(test_cases).where(test_cases.c.problem_id == pid))
            conn.execute(delete(problems).where(problems.c.id == pid))
        return {"deleted": pid}

    @app.put("/api/test_cases/{cid}")
    def update_case(cid: int, payload: dict[str, Any]) -> dict[str, Any]:
        values = {k: v for k, v in payload.items() if k in _CASE_EDITABLE}
        if not values:
            raise HTTPException(status_code=400, detail="no editable field in payload")
        with engine.begin() as conn:
            res = conn.execute(
                update(test_cases).where(test_cases.c.id == cid).values(**values)
            )
            if res.rowcount == 0:
                raise HTTPException(status_code=404, detail="test case not found")
            row = (
                conn.execute(select(test_cases).where(test_cases.c.id == cid))
                .mappings()
                .first()
            )
        assert row is not None
        return dict(row)

    @app.delete("/api/test_cases/{cid}")
    def delete_case(cid: int) -> dict[str, Any]:
        with engine.begin() as conn:
            res = conn.execute(delete(test_cases).where(test_cases.c.id == cid))
            if res.rowcount == 0:
                raise HTTPException(status_code=404, detail="test case not found")
        return {"deleted": cid}

    @app.post("/api/problems/{pid}/test_cases", status_code=201)
    def add_case(pid: str, payload: dict[str, Any]) -> dict[str, Any]:
        with engine.begin() as conn:
            exists = conn.execute(
                select(problems.c.id).where(problems.c.id == pid)
            ).first()
            if exists is None:
                raise HTTPException(status_code=404, detail="problem not found")
            next_seq = (
                int(
                    conn.execute(
                        select(func.coalesce(func.max(test_cases.c.seq), -1)).where(
                            test_cases.c.problem_id == pid
                        )
                    ).scalar()
                    or -1
                )
                + 1
            )
            res = conn.execute(
                insert(test_cases).values(
                    problem_id=pid,
                    seq=payload.get("seq", next_seq),
                    input=payload.get("input", ""),
                    expected=payload.get("expected", ""),
                    category=payload.get("category"),
                )
            )
            pk = res.inserted_primary_key
            assert pk is not None
            new_id = pk[0]
            row = (
                conn.execute(select(test_cases).where(test_cases.c.id == new_id))
                .mappings()
                .first()
            )
        assert row is not None
        return dict(row)

    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="IPE 문제 은행 관리 콘솔")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("IPE_ADMIN_DB_URL"),
        help="SQLAlchemy URL (예: postgresql+psycopg://USER:PW@127.0.0.1:16380/fly-db). "
        "미지정 시 env IPE_ADMIN_DB_URL.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8800)
    args = parser.parse_args(argv)
    if not args.db_url:
        raise SystemExit("--db-url 또는 env IPE_ADMIN_DB_URL 필요 (비밀번호는 소스 비포함)")

    import uvicorn
    from sqlalchemy import create_engine

    engine = create_engine(args.db_url, pool_pre_ping=True)
    app = create_admin_app(engine)
    print(f"[admin] 문제 은행 관리 콘솔 → http://{args.host}:{args.port}", flush=True)
    print(f"[admin] DB → {args.db_url.rsplit('@', 1)[-1]}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
