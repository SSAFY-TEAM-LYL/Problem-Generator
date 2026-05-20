"""Catalog CLI — 사람 review + 운영 도구.

사용 예::

    python -m ipe.catalog list                          # 전체 목록
    python -m ipe.catalog list --status draft           # draft만
    python -m ipe.catalog show p_abc123                 # problem.md 출력
    python -m ipe.catalog approve p_abc123 --by minsu   # status='approved'
    python -m ipe.catalog reject p_abc123 --note "..."  # status='rejected'
    python -m ipe.catalog promote <run_id>              # 수동 promote (이미 success run만)

기본 catalog root: ``outputs/catalog``. ``--catalog-root`` 로 override.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from ipe.catalog.store import (
    DEFAULT_CATALOG_ROOT,
    CatalogEntry,
    ReviewStatus,
    find,
    list_entries,
    promote_run,
    set_status,
)
from ipe.state import ProblemState

_STATUS_CHOICES: tuple[str, ...] = ("draft", "approved", "rejected")


def _print_table(entries: list[CatalogEntry]) -> None:
    """간단한 stdout 표 — id / status / algorithm / title / difficulty."""
    if not entries:
        print("(no entries)")
        return
    print(f"{'ID':<16} {'STATUS':<10} {'ALGO':<14} {'DIFF':<14} TITLE")
    print("-" * 100)
    for e in entries:
        title = str(e.get("title") or "")
        if len(title) > 50:
            title = title[:47] + "..."
        diff = str(e.get("difficulty_label") or "-")
        print(
            f"{e.get('id', '?'):<16} "
            f"{e.get('status', '?'):<10} "
            f"{e.get('algorithm', '?'):<14} "
            f"{diff:<14} "
            f"{title}"
        )


def _cmd_list(args: argparse.Namespace) -> int:
    status: ReviewStatus | None = args.status
    entries = list_entries(status=status, catalog_root=args.catalog_root)
    if args.json:
        for e in entries:
            print(json.dumps(e, ensure_ascii=False))
    else:
        _print_table(entries)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    entry = find(args.id, catalog_root=args.catalog_root)
    if entry is None:
        print(f"error: problem not found: {args.id}", file=sys.stderr)
        return 2
    if args.meta:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return 0
    link = args.catalog_root / "problems" / args.id
    md_path = link / "problem.md"
    if not md_path.exists():
        print(f"error: problem.md not found at {md_path}", file=sys.stderr)
        return 3
    print(md_path.read_text(encoding="utf-8"))
    return 0


def _set_status_cmd(
    args: argparse.Namespace, new_status: ReviewStatus
) -> int:
    try:
        updated = set_status(
            args.id,
            new_status,
            by=args.by,
            note=args.note,
            catalog_root=args.catalog_root,
        )
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(
        f"{args.id} → status={updated.get('status')} "
        f"by={updated.get('reviewed_by') or '(unknown)'} "
        f"at={updated.get('reviewed_at')}"
    )
    if updated.get("review_note"):
        print(f"  note: {updated.get('review_note')}")
    return 0


def _cmd_approve(args: argparse.Namespace) -> int:
    return _set_status_cmd(args, "approved")


def _cmd_reject(args: argparse.Namespace) -> int:
    return _set_status_cmd(args, "rejected")


def _cmd_promote(args: argparse.Namespace) -> int:
    """수동 promote — 이미 ``outputs/<run_id>/problem.json`` 이 있는 run을 catalog로."""
    run_dir = Path(args.outputs_root) / args.run_id
    if not run_dir.exists():
        print(f"error: run_dir not found: {run_dir}", file=sys.stderr)
        return 2
    problem_json = run_dir / "problem.json"
    if not problem_json.exists():
        print(f"error: problem.json not found in {run_dir}", file=sys.stderr)
        return 3

    doc: dict[str, Any] = json.loads(problem_json.read_text(encoding="utf-8"))
    problem = doc.get("problem") or {}
    cs = doc.get("constraints_structured") or {}
    diff = doc.get("difficulty") or {}
    meta = doc.get("meta") or {}
    state_view: dict[str, Any] = {
        "problem_title": problem.get("title") or "(untitled)",
        "target_algorithm": meta.get("target_algorithm") or "",
        "target_language": meta.get("target_language") or "python",
        "constraints_structured": cs,
        "sample_testcases": problem.get("sample_testcases") or [],
        "testcases": doc.get("testcases_inline") or [],
        "difficulty_label": diff.get("label"),
    }
    entry = promote_run(
        cast(ProblemState, state_view),
        run_dir,
        args.run_id,
        catalog_root=args.catalog_root,
    )
    print(f"promoted: {entry.get('id')} (status={entry.get('status')})")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ipe.catalog",
        description="Problem catalog — promote / list / review",
    )
    parser.add_argument(
        "--catalog-root",
        type=Path,
        default=DEFAULT_CATALOG_ROOT,
        help=f"catalog root (default: {DEFAULT_CATALOG_ROOT})",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="목록 출력")
    p_list.add_argument(
        "--status",
        choices=_STATUS_CHOICES,
        default=None,
        help="status filter",
    )
    p_list.add_argument("--json", action="store_true", help="JSONL 형식 출력")
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="problem.md 또는 metadata 출력")
    p_show.add_argument("id", help="problem id (e.g. p_abc123)")
    p_show.add_argument(
        "--meta", action="store_true",
        help="problem.md 대신 entry metadata (JSON) 출력",
    )
    p_show.set_defaults(func=_cmd_show)

    for name, cmd_fn in [("approve", _cmd_approve), ("reject", _cmd_reject)]:
        p = sub.add_parser(name, help=f"status='{name}d' 로 갱신")
        p.add_argument("id", help="problem id")
        p.add_argument("--by", default=None, help="reviewer 이름")
        p.add_argument("--note", default=None, help="review note")
        p.set_defaults(func=cmd_fn)

    p_prom = sub.add_parser("promote", help="기존 run을 catalog에 등록 (idempotent)")
    p_prom.add_argument("run_id", help="outputs/<run_id> 의 run_id")
    p_prom.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="outputs/ root (default: outputs)",
    )
    p_prom.set_defaults(func=_cmd_promote)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
