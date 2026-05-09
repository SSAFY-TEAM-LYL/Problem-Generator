"""Markdown 렌더 — ``problem.md`` 빌더 (P10 audit E1 분리).

근거: ``ipe/io.py`` 348 lines > ROADMAP §2 budget ≤280 → markdown 렌더 부분만
별도 모듈로 추출 (-82 줄). ``ipe.io.save_result`` 가 ``_build_difficulty`` 결과를
인자로 전달하여 순환 import 회피.

함수:
- ``render_problem_md(state, *, manifest, difficulty)``: 사람용 markdown.
"""

from __future__ import annotations

from typing import Any

from ipe.state import ProblemState


def render_problem_md(
    state: ProblemState,
    *,
    manifest: list[dict[str, Any]],
    difficulty: dict[str, Any] | None = None,
) -> str:
    """사람용 markdown 렌더 — 문제 / 제약 / 샘플 / 솔루션 / 난이도 / manifest 표.

    Args:
        state: ProblemState — title/description/constraints/samples/solution
        manifest: testcase manifest (``ipe.io._build_testcase_manifest`` 결과)
        difficulty: ``ipe.io._build_difficulty`` 결과 — None 시 Difficulty 섹션 생략
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

    if difficulty:
        lines += [
            "## Difficulty",
            "",
            f"**Label:** {difficulty['label']}",
            "",
            f"**Reasoning:** {difficulty.get('reasoning') or ''}",
            "",
        ]
        anchors = difficulty.get("calibration_anchors") or []
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
