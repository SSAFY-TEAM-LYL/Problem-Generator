"""Calibration anchors 단위 테스트 (P9.1).

스펙: ARCHITECTURE.md §3.10, IMPLEMENTATION_ROADMAP §1 P9.1
범위: ``load_anchors`` 의 fallback 경로 + 기본 anchors.json 무결성.
"""

from __future__ import annotations

import json
from pathlib import Path

from ipe.calibration import ANCHORS_PATH, load_anchors


def test_default_anchors_load() -> None:
    """프로젝트 default anchors.json은 4~8개 anchor를 포함."""
    anchors = load_anchors()
    assert 4 <= len(anchors) <= 8
    # 모든 entry가 (id, label, summary, factors) 4개 필드를 보유
    for a in anchors:
        assert "id" in a and isinstance(a["id"], str)
        assert "label" in a and isinstance(a["label"], str)
        assert "summary" in a and isinstance(a["summary"], str)
        assert "factors" in a and isinstance(a["factors"], dict)


def test_default_anchors_path_exists() -> None:
    """기본 anchors.json 경로는 패키지 안에 존재."""
    assert ANCHORS_PATH.exists()
    assert ANCHORS_PATH.name == "anchors.json"


def test_load_anchors_missing_file_returns_empty(tmp_path: Path) -> None:
    """파일이 없으면 빈 list 반환 (raise 안 함)."""
    missing = tmp_path / "no_such.json"
    assert load_anchors(missing) == []


def test_load_anchors_malformed_json_returns_empty(tmp_path: Path) -> None:
    """JSON 파싱 실패 시 빈 list 반환."""
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    assert load_anchors(bad) == []


def test_load_anchors_non_list_returns_empty(tmp_path: Path) -> None:
    """top-level이 list가 아니면 빈 list 반환."""
    obj = tmp_path / "obj.json"
    obj.write_text(json.dumps({"id": "x"}), encoding="utf-8")
    assert load_anchors(obj) == []


def test_load_anchors_filters_non_dict_entries(tmp_path: Path) -> None:
    """list 안의 dict가 아닌 entry는 필터링."""
    mixed = tmp_path / "mixed.json"
    mixed.write_text(
        json.dumps([{"id": "ok"}, "not_a_dict", 42, {"id": "ok2"}]),
        encoding="utf-8",
    )
    out = load_anchors(mixed)
    assert len(out) == 2
    assert all(isinstance(a, dict) for a in out)
