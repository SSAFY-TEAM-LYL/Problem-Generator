"""산출물 영속화 (P10) — 최종 state를 ``outputs/<run_id>/`` Polygon 스타일로 저장.

스펙: PROJECT_SPEC.md §6 (산출물 구조), IMPLEMENTATION_ROADMAP §1 P10

생성하는 파일:
- ``problem.json`` — SPEC §6 schema (DB 인서트 가능한 정형 데이터)
- ``problem.md`` — 사람이 읽는 markdown
- ``solution.py`` 또는 ``Solution.java``
- ``generators/<name>.py`` — 시드 기반 입력 생성기 (Phase C 통과 시)
- ``tests/<NN>.in / <NN>.out`` — 1-indexed zero-padded testcase
- ``tests/manifest.json`` — 각 case 메타 (kind, category, generator, seed, exec_time_ms)
- ``outputs/by-name/<timestamp>_<algo>`` → ``<run_id>`` symlink (충돌 시 skip)

``llm_traces/`` 와 ``checkpoint.db`` 는 LLMCallTracker / SqliteSaver 가 이미 작성.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ipe.state import LLMCallRecord, ProblemState

OUTPUTS_ROOT = Path("outputs")
BY_NAME_ROOT = OUTPUTS_ROOT / "by-name"

_SLUG_REPLACE_RE = re.compile(r"[^A-Za-z0-9_-]+")
_SLUG_DEDUP_RE = re.compile(r"_+")


def _slug(text: str, *, max_len: int = 64) -> str:
    """공백/한글/특수문자를 underscore로 변환 + 영숫자/`-`/`_`만 유지.

    - 빈 입력 → ``"unnamed"``
    - 연속 underscore는 1개로 압축
    - 길이 ``max_len`` 으로 절단
    """
    if not text:
        return "unnamed"
    s = _SLUG_REPLACE_RE.sub("_", text.strip())
    s = _SLUG_DEDUP_RE.sub("_", s).strip("_")
    if not s:
        return "unnamed"
    return s[:max_len]


def _summarize_llm_calls(
    calls: list[LLMCallRecord],
) -> dict[str, Any]:
    """SPEC §6 meta.llm_call_summary 빌드."""
    by_node: dict[str, int] = {}
    total_in = 0
    total_out = 0
    total_cost = 0.0
    for c in calls:
        node = str(c.get("node", "unknown"))
        by_node[node] = by_node.get(node, 0) + 1
        total_in += int(c.get("input_tokens", 0))
        total_out += int(c.get("output_tokens", 0))
        total_cost += float(c.get("cost_usd", 0.0))
    return {
        "total_calls": len(calls),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_cost_usd": round(total_cost, 6),
        "by_node": by_node,
    }


def _build_meta(state: ProblemState, *, generated_at: str) -> dict[str, Any]:
    return {
        "run_id": state.get("run_id"),
        "target_algorithm": state.get("target_algorithm"),
        "target_language": state.get("target_language"),
        "iteration_count": state.get("iteration_count", 0),
        "final_status": state.get("final_status"),
        "generated_at": generated_at,
        "llm_call_summary": _summarize_llm_calls(
            list(state.get("llm_calls") or [])
        ),
    }


def _build_difficulty(state: ProblemState) -> dict[str, Any] | None:
    """difficulty_* 4 필드 → SPEC §6 difficulty 블록.

    P9 evaluator 미실행 또는 parse 실패 시 None 반환.
    """
    label = state.get("difficulty_label")
    if not label:
        return None
    used = state.get("difficulty_calibration_anchors") or []
    return {
        "label": label,
        "reasoning": state.get("difficulty_reasoning"),
        "factors": state.get("difficulty_factors") or {},
        "calibration_anchors": [a.get("id") for a in used if isinstance(a, dict)],
    }


def _build_problem_block(state: ProblemState) -> dict[str, Any]:
    return {
        "title": state.get("problem_title"),
        "description": state.get("problem_description"),
        "constraints": state.get("constraints"),
        "has_special_judge": state.get("has_special_judge", False),
        "special_judge_code": state.get("special_judge_code"),
        "sample_testcases": state.get("sample_testcases") or [],
    }


def _build_solution_block(state: ProblemState) -> dict[str, Any]:
    return {
        "language": state.get("target_language"),
        "code": state.get("solution_code"),
    }


def _build_testcase_manifest(testcases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """tests/manifest.json 용 케이스별 메타 list."""
    out: list[dict[str, Any]] = []
    for idx, tc in enumerate(testcases, start=1):
        out.append({
            "index": idx,
            "filename": f"{idx:02d}",
            "kind": tc.get("kind"),
            "category": tc.get("category"),
            "generator": tc.get("generator"),
            "seed": tc.get("seed"),
            "exec_time_ms": tc.get("execution_time_ms"),
        })
    return out


def _write_solution(run_dir: Path, language: str, code: str) -> str:
    """solution.py / Solution.java 작성 후 파일명 반환."""
    path = run_dir / ("Solution.java" if language == "java" else "solution.py")
    path.write_text(code or "", encoding="utf-8")
    return path.name


def _write_generators(run_dir: Path, generators: list[dict[str, Any]]) -> None:
    if not generators:
        return
    gen_dir = run_dir / "generators"
    gen_dir.mkdir(parents=True, exist_ok=True)
    for g in generators:
        name = g.get("name") or "unnamed"
        code = g.get("code") or ""
        (gen_dir / f"{name}.py").write_text(code, encoding="utf-8")


def _write_testcases(
    run_dir: Path, testcases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """tests/<NN>.in / <NN>.out + manifest.json 작성. manifest를 반환."""
    if not testcases:
        return []
    tests_dir = run_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    for idx, tc in enumerate(testcases, start=1):
        (tests_dir / f"{idx:02d}.in").write_text(
            str(tc.get("input", "")), encoding="utf-8"
        )
        (tests_dir / f"{idx:02d}.out").write_text(
            str(tc.get("expected_output", "")), encoding="utf-8"
        )
    manifest = _build_testcase_manifest(testcases)
    (tests_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def _render_problem_md(state: ProblemState, manifest: list[dict[str, Any]]) -> str:
    """사람용 markdown 렌더 — 문제 / 제약 / 샘플 / 솔루션 / 난이도 블록.

    P10.2 — `problem.md` 단일 파일 출력. 코드는 fenced block, 표는 GFM.
    """
    title = state.get("problem_title") or state.get("target_algorithm") or "Untitled"
    lines: list[str] = [f"# {title}", ""]

    desc = state.get("problem_description")
    if desc:
        lines += ["## Description", "", str(desc), ""]

    constraints = state.get("constraints")
    if constraints:
        lines += ["## Constraints", "", str(constraints), ""]

    samples = state.get("sample_testcases") or []
    if samples:
        lines += ["## Sample Testcases", ""]
        for i, tc in enumerate(samples, start=1):
            inp = str(tc.get("input", "")).rstrip()
            out = str(tc.get("expected_output", "")).rstrip()
            lines += [
                f"### Sample {i}",
                "",
                "Input:",
                "```",
                inp,
                "```",
                "",
                "Output:",
                "```",
                out,
                "```",
                "",
            ]

    diff = _build_difficulty(state)
    if diff:
        lines += [
            "## Difficulty",
            "",
            f"**Label:** {diff['label']}",
            "",
            f"**Reasoning:** {diff.get('reasoning') or ''}",
            "",
        ]
        anchors = diff.get("calibration_anchors") or []
        if anchors:
            lines += [f"**Calibration anchors:** {', '.join(anchors)}", ""]

    lang = state.get("target_language") or "python"
    code = state.get("solution_code")
    if code:
        fence_lang = "java" if lang == "java" else "python"
        lines += [
            "## Golden Solution",
            "",
            f"```{fence_lang}",
            str(code).rstrip(),
            "```",
            "",
        ]

    if manifest:
        lines += [
            "## Testcase Manifest",
            "",
            "| # | kind | category | generator | seed | exec (ms) |",
            "|---|---|---|---|---|---|",
        ]
        for m in manifest:
            lines.append(
                f"| {m['index']:02d} | {m.get('kind') or '-'} | "
                f"{m.get('category') or '-'} | {m.get('generator') or '-'} | "
                f"{m.get('seed') if m.get('seed') is not None else '-'} | "
                f"{m.get('exec_time_ms') if m.get('exec_time_ms') is not None else '-'} |"
            )
        lines.append("")

    return "\n".join(lines)


def _create_by_name_symlink(
    run_dir: Path,
    *,
    algorithm: str,
    timestamp: str,
    by_name_root: Path = BY_NAME_ROOT,
) -> Path | None:
    """``outputs/by-name/<timestamp>_<algo_slug>`` symlink 생성.

    이미 존재하면 skip (return None). 충돌 회피 — 같은 timestamp+algo는 거의 없으나
    안전하게.
    """
    by_name_root.mkdir(parents=True, exist_ok=True)
    name = f"{timestamp}_{_slug(algorithm)}"
    link = by_name_root / name
    if link.exists() or link.is_symlink():
        return None
    # 상대경로로 symlink — outputs/by-name/<name> → ../<run_id>
    rel_target = Path("..") / run_dir.name
    os.symlink(rel_target, link)
    return link


def save_result(
    state: ProblemState,
    run_dir: Path,
    *,
    by_name_root: Path = BY_NAME_ROOT,
) -> dict[str, Any]:
    """final_state를 ``run_dir`` 에 SPEC §6 Polygon 스타일로 저장.

    Args:
        state: 최종 ProblemState (final_status='success' 또는 halt 모두 가능)
        run_dir: ``outputs/<run_id>/`` 디렉토리. main.py가 이미 생성.
        by_name_root: by-name symlink root (테스트용 override).

    Returns:
        problem.json의 dict 본문 (확인용).
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. solution / generators / tests
    language = str(state.get("target_language") or "python")
    code = str(state.get("solution_code") or "")
    if code:
        _write_solution(run_dir, language, code)
    _write_generators(run_dir, list(state.get("generators") or []))
    testcases = list(state.get("testcases") or [])
    manifest = _write_testcases(run_dir, testcases)

    # 2. problem.json
    problem_doc: dict[str, Any] = {
        "meta": _build_meta(state, generated_at=generated_at),
        "constraints_structured": state.get("constraints_structured") or {},
        "iteration_history": list(state.get("iteration_history") or []),
        "problem": _build_problem_block(state),
        "solution": _build_solution_block(state),
        "generators": list(state.get("generators") or []),
        "testcases_inline": testcases,
        "testcase_manifest": manifest,
        "execution_results": list(state.get("execution_results") or []),
        "llm_calls": list(state.get("llm_calls") or []),
    }
    diff = _build_difficulty(state)
    if diff is not None:
        problem_doc["difficulty"] = diff
    (run_dir / "problem.json").write_text(
        json.dumps(problem_doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 3. problem.md
    (run_dir / "problem.md").write_text(
        _render_problem_md(state, manifest), encoding="utf-8"
    )

    # 4. by-name symlink (충돌 시 skip)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    algo = str(state.get("target_algorithm") or "unnamed")
    _create_by_name_symlink(
        run_dir,
        algorithm=algo,
        timestamp=timestamp,
        by_name_root=by_name_root,
    )

    return problem_doc
