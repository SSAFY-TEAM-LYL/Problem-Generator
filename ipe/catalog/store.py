"""Catalog store — JSONL index + symlink farm for promoted problems.

설계 결정:
- **JSONL** (1 line/problem): line-oriented append + 부분 rewrite 쉬움. SQL DB
  ingest도 쉬움 (line-by-line bulk insert).
- **Symlink farm**: storage 중복 회피. ``outputs/catalog/problems/<id>/`` 가
  ``outputs/<run_id>/`` 로 symlink. 백엔드는 catalog/ 만 mount하면 됨.
- **Idempotent promote**: 같은 ``run_id`` 가 이미 catalog에 있으면 기존 entry
  반환 (재실행 안전). status는 기존 값 보존.
- **No DB dependency**: pure Python + stdlib. 백엔드가 자체 DB를 가져도 sync
  쉬움 (JSONL → seed).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict, cast

from ipe.state import ProblemState

# CLI/io에서 override 가능
DEFAULT_CATALOG_ROOT = Path("outputs") / "catalog"

ReviewStatus = Literal["draft", "approved", "rejected"]
_VALID_STATUSES: frozenset[str] = frozenset({"draft", "approved", "rejected"})


class CatalogEntry(TypedDict, total=False):
    """problems.jsonl 한 row의 schema. 백엔드가 DB ingest 가능한 정형 데이터."""

    id: str  # ``p_<12hex>`` — run_id + title 기반 deterministic hash
    run_id: str
    algorithm: str
    language: str
    title: str
    difficulty_label: str | None
    time_limit_ms: int
    memory_limit_mb: int
    sample_count: int
    testcase_count: int
    created_at: str  # ISO-8601 UTC with ``Z``
    status: ReviewStatus
    reviewed_by: str | None
    reviewed_at: str | None
    review_note: str | None
    tags: list[str]


def _problem_id(run_id: str, title: str) -> str:
    """``p_<12hex>`` — run_id + title 결정적 hash. 같은 run + title 은 같은 id."""
    h = hashlib.sha1(f"{run_id}|{title}".encode()).hexdigest()[:12]
    return f"p_{h}"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _jsonl_path(root: Path) -> Path:
    return root / "problems.jsonl"


def _problems_dir(root: Path) -> Path:
    return root / "problems"


def _read_all(root: Path) -> list[CatalogEntry]:
    """JSONL 전체 읽기. 파일 없으면 빈 리스트."""
    p = _jsonl_path(root)
    if not p.exists():
        return []
    out: list[CatalogEntry] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # 손상된 line은 skip + 경고 (운영 안정성 — 한 row 깨져도 다른 row 살림)
            continue
        if isinstance(entry, dict):
            out.append(cast(CatalogEntry, entry))
    return out


def _write_all(root: Path, entries: list[CatalogEntry]) -> None:
    """JSONL 전체 rewrite — atomic은 아니지만 single-writer 가정 (CLI/save_result 직렬)."""
    root.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
    _jsonl_path(root).write_text(body + ("\n" if body else ""), encoding="utf-8")


def _make_symlink(run_dir: Path, problem_id: str, root: Path) -> Path:
    """``catalog/problems/<id>`` → ``run_dir`` symlink 생성 (idempotent)."""
    problems_dir = _problems_dir(root)
    problems_dir.mkdir(parents=True, exist_ok=True)
    link = problems_dir / problem_id

    # 이미 link 존재 + 같은 target이면 skip. 다른 target이면 replace.
    if link.is_symlink() or link.exists():
        try:
            existing = link.readlink() if link.is_symlink() else None
        except (OSError, RuntimeError):
            existing = None
        if existing is not None:
            # readlink가 relative면 link의 parent 기준으로 resolve
            existing_abs = (
                Path(existing).resolve()
                if Path(existing).is_absolute()
                else (link.parent / existing).resolve()
            )
            if existing_abs == run_dir.resolve():
                return link
        link.unlink(missing_ok=True)

    # relative symlink (백엔드 mount 이동 시 안전).
    try:
        rel = run_dir.resolve().relative_to(problems_dir.resolve().parent.parent)
        link.symlink_to(Path("..") / ".." / rel)
    except (ValueError, OSError):
        # 다른 파일 시스템 등 fallback: absolute
        link.symlink_to(run_dir.resolve())
    return link


def _build_entry(
    state: ProblemState, run_id: str, *, title: str
) -> CatalogEntry:
    cs = state.get("constraints_structured") or {}
    samples = state.get("sample_testcases") or []
    testcases = state.get("testcases") or []
    diff_label_raw = state.get("difficulty_label")
    diff_label: str | None = str(diff_label_raw) if diff_label_raw else None
    return {
        "id": _problem_id(run_id, title),
        "run_id": run_id,
        "algorithm": str(state.get("target_algorithm") or ""),
        "language": str(state.get("target_language") or "python"),
        "title": title,
        "difficulty_label": diff_label,
        "time_limit_ms": int(cs.get("time_limit_ms") or 0),
        "memory_limit_mb": int(cs.get("memory_limit_mb") or 0),
        "sample_count": len(samples) if isinstance(samples, list) else 0,
        "testcase_count": len(testcases) if isinstance(testcases, list) else 0,
        "created_at": _now_iso(),
        "status": "draft",
        "reviewed_by": None,
        "reviewed_at": None,
        "review_note": None,
        "tags": [],
    }


def promote_run(
    state: ProblemState,
    run_dir: Path,
    run_id: str,
    *,
    catalog_root: Path = DEFAULT_CATALOG_ROOT,
) -> CatalogEntry:
    """성공 run을 catalog로 promote. ``final_status="success"`` 가 아닌 run도
    호출자 책임 하에 강제 가능 (CLI ``promote``).

    Idempotent: 같은 run_id가 이미 있으면 기존 entry 반환 (status 보존).

    Returns:
        promote된 (또는 기존) CatalogEntry.
    """
    catalog_root.mkdir(parents=True, exist_ok=True)

    title = str(state.get("problem_title") or "(untitled)")
    new_entry = _build_entry(state, run_id, title=title)

    entries = _read_all(catalog_root)
    for existing in entries:
        if existing.get("run_id") == run_id:
            # 이미 등록 → symlink만 보장하고 기존 entry 반환
            _make_symlink(
                run_dir, str(existing.get("id") or new_entry["id"]), catalog_root
            )
            return existing

    entries.append(new_entry)
    _write_all(catalog_root, entries)
    _make_symlink(run_dir, new_entry["id"], catalog_root)
    return new_entry


def list_entries(
    *,
    status: ReviewStatus | None = None,
    catalog_root: Path = DEFAULT_CATALOG_ROOT,
) -> list[CatalogEntry]:
    """전체 또는 status로 필터링한 entry 리스트.

    Args:
        status: ``"draft"`` / ``"approved"`` / ``"rejected"`` / None (all).
    """
    entries = _read_all(catalog_root)
    if status is None:
        return entries
    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r} (valid: {sorted(_VALID_STATUSES)})")
    return [e for e in entries if e.get("status") == status]


def find(
    problem_id: str,
    *,
    catalog_root: Path = DEFAULT_CATALOG_ROOT,
) -> CatalogEntry | None:
    """ID로 단일 entry 조회. 없으면 None."""
    for entry in _read_all(catalog_root):
        if entry.get("id") == problem_id:
            return entry
    return None


def set_status(
    problem_id: str,
    new_status: ReviewStatus,
    *,
    by: str | None = None,
    note: str | None = None,
    catalog_root: Path = DEFAULT_CATALOG_ROOT,
) -> CatalogEntry:
    """review status 갱신 + reviewed_at/by/note 기록.

    Raises:
        KeyError: problem_id가 catalog에 없으면.
        ValueError: new_status가 valid 아니면.
    """
    if new_status not in _VALID_STATUSES:
        raise ValueError(
            f"invalid status: {new_status!r} (valid: {sorted(_VALID_STATUSES)})"
        )

    entries = _read_all(catalog_root)
    updated: CatalogEntry | None = None
    for i, entry in enumerate(entries):
        if entry.get("id") == problem_id:
            # 불변성: 새 dict 생성, 기존 entry는 mutate 안 함
            new_entry: CatalogEntry = {**entry}
            new_entry["status"] = new_status
            new_entry["reviewed_at"] = _now_iso()
            new_entry["reviewed_by"] = by
            new_entry["review_note"] = note
            entries[i] = new_entry
            updated = new_entry
            break

    if updated is None:
        raise KeyError(f"problem not found in catalog: {problem_id!r}")

    _write_all(catalog_root, entries)
    return updated
