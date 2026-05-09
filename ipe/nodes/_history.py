"""iteration_history → user prompt section 변환 (P7.3).

스펙: ARCHITECTURE.md §3.4, IMPLEMENTATION_ROADMAP §1 P7.3
근거: REVIEW W4 oscillation 방지 — 같은 ``error_signature``가 반복되면
LLM에게 "근본적으로 다른 전략" 강한 경고를 prompt에 삽입.

graph.py의 ``decision`` 노드가 매 사이클 ``iteration_history`` 항목을
누적한다. 본 헬퍼는 다음 cycle에서 노드(architect/coder/auditor/generator)
가 user prompt 끝에 첨부할 markdown 섹션을 생성한다.

호출부 패턴::

    user = USER_TEMPLATE.format(...)
    if feedback := state.get("feedback_message"):
        user += FEEDBACK_SUFFIX.format(feedback=feedback)
    user += build_history_section(state, current_node="coder")
"""

from __future__ import annotations

from ipe.state import ProblemState

DEFAULT_MAX_ENTRIES = 5
FEEDBACK_EXCERPT_CHARS = 200
OSCILLATION_THRESHOLD = 2  # 같은 (node, error_signature) 2회 이상 → 강한 경고


def build_history_section(
    state: ProblemState,
    *,
    current_node: str,
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> str:
    """``iteration_history`` 최근 항목들을 markdown 섹션으로 변환.

    Args:
        state: ProblemState — ``iteration_history`` 키를 읽음
        current_node: 호출 노드 이름 — oscillation 감지 시 자기 자신의
            반복만 검사 (다른 노드의 반복은 본인과 무관)
        max_entries: 표시할 최근 entries 수

    Returns:
        prompt에 append할 markdown. history가 비어있으면 빈 문자열.

    동일 ``(current_node, error_signature)``가 ``OSCILLATION_THRESHOLD`` 회
    이상 발견되면 섹션 끝에 강한 경고를 추가한다 — 같은 실수를 반복하는
    LLM에게 다른 전략을 요구.
    """
    history = state.get("iteration_history") or []
    if not history:
        return ""

    recent = list(history[-max_entries:])

    # 자기 자신 노드의 error_signature 카운트
    own_sigs: dict[str, int] = {}
    for r in recent:
        if r.get("node") != current_node:
            continue
        sig = r.get("error_signature") or ""
        if not sig:
            continue
        own_sigs[sig] = own_sigs.get(sig, 0) + 1
    repeated = [s for s, n in own_sigs.items() if n >= OSCILLATION_THRESHOLD]

    lines = ["", "## Previous Attempts", ""]
    for r in recent:
        idx = r.get("iter_index", "?")
        node = r.get("node", "?")
        sig = r.get("error_signature") or "—"
        feedback = (r.get("feedback") or "").replace("\n", " ")[:FEEDBACK_EXCERPT_CHARS]
        lines.append(f"- [iter {idx}] {node} ({sig}): {feedback}")

    if repeated:
        lines.append("")
        lines.append(
            "⚠️ **DIFFERENT STRATEGY REQUIRED** — your previous attempts "
            f"produced the same error signature(s) {repeated}. "
            "Do NOT repeat the same approach; switch to a fundamentally "
            "different strategy."
        )

    return "\n".join(lines) + "\n"
