"""Problem Catalog 영속화 — 생성된 문제를 사람 review + 웹 백엔드용으로 indexing.

스펙: docs/catalog/SCHEMA.md (이 PR에서 같이 작성)

구조:
- ``outputs/catalog/problems.jsonl`` — 1 row/problem (index)
- ``outputs/catalog/problems/<id>/`` — symlink → ``outputs/<run_id>/`` (storage 중복 회피)

진입점:
- ``promote_run(state, run_dir)`` — success run을 catalog로 promote (idempotent)
- ``list_entries(status=None)`` — JSONL 읽기
- ``set_status(problem_id, status, by=None, note=None)`` — review status 갱신
- ``find(problem_id)`` — 단일 entry 조회

CLI: ``python -m ipe.catalog <command>`` (promote / list / show / approve / reject).
"""

from __future__ import annotations

from ipe.catalog.store import (
    DEFAULT_CATALOG_ROOT,
    CatalogEntry,
    ReviewStatus,
    find,
    list_entries,
    promote_run,
    set_status,
)

__all__ = [
    "CatalogEntry",
    "DEFAULT_CATALOG_ROOT",
    "ReviewStatus",
    "find",
    "list_entries",
    "promote_run",
    "set_status",
]
