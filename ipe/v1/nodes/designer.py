"""designer 노드 — ProblemSpec → AlgorithmDesign (D안 PR-A3).

LLM: Sonnet 4.6 (M1 패턴 유지 — Coder 분해의 designer 측, Opus 대비 cost 절감).

핵심 책임: Coder 가 implement 할 algorithm 의 pseudocode + complexity bound +
**invariants** 산출. Phase 1 = Dijkstra MVR — invariants 가 PR-A2 의
DijkstraVerifier 4 kinds 와 1:1 매핑되어야 verifier dispatch 가 의미.

Phase 1 단순화: prompt 가 Dijkstra default invariants 4종을 LLM 에 명시적 가이드.
Phase 2 에서 algorithm 별 standard invariants dict 화.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ..schema import AlgorithmDesign
from ..state import V1State

DESIGNER_MODEL = "claude-sonnet-4-6"
DESIGNER_TEMPERATURE = 0.2


DIJKSTRA_DEFAULT_INVARIANTS: tuple[tuple[str, str], ...] = (
    ("non_negative_distance", "모든 결과 거리 >= 0 (unreachable 은 -1)"),
    ("source_zero", "s == t 일 때 결과 = 0"),
    ("reachability_consistent", "BFS 도달가능성과 결과의 UNREACHABLE 여부 일치"),
    (
        "shortest_distance_optimal",
        "Bellman-Ford golden 과 일치 (non-negative weight 가정)",
    ),
)


_SYSTEM_PROMPT = """\
당신은 algorithm designer 이다. 주어진 ProblemSpec 에 대해 typed AlgorithmDesign
을 산출한다 (구조화된 tool call 로 반환).

요구사항:
- algorithm_name: 사용할 algorithm 이름 (예: "Dijkstra")
- complexity_target: time_big_o + space_big_o (예: "O((V+E) log V)", "O(V+E)")
- pseudocode: 자연어 step list (Coder 힌트)
- edge_cases: 위험 케이스 list (name + description, optional example_input)
- invariants: symbolic verifier 가 검증할 algorithm-specific 수학적 성질의 list.
  각 invariant 는 kind + description + (optional) formal_statement.

target_algorithm = "dijkstra" 면 다음 4 invariants 를 반드시 포함:
- non_negative_distance
- source_zero
- reachability_consistent
- shortest_distance_optimal

위 kind 들은 verifier dispatch key 이므로 정확한 spelling 필수.

- data_structures: 사용할 자료구조 list (예: ["priority_queue", "adjacency_list"])
"""


def _default_invariants_for(target_algorithm: str) -> list[tuple[str, str]]:
    if target_algorithm == "dijkstra":
        return list(DIJKSTRA_DEFAULT_INVARIANTS)
    return []


def _build_user_prompt(state: V1State) -> str:
    spec = state.spec
    if spec is None:
        msg = "designer requires state.spec — architect must run first"
        raise ValueError(msg)
    parts = [
        f"target_algorithm: {state.target_algorithm.value}",
        f"problem title: {spec.title}",
        f"description: {spec.description}",
        f"io_contract.input_format: {spec.io_contract.input_format}",
        f"io_contract.output_format: {spec.io_contract.output_format}",
        f"constraints: {[c.name for c in spec.constraints]}",
        f"sample count: {len(spec.sample_testcases)}",
    ]
    defaults = _default_invariants_for(state.target_algorithm.value)
    if defaults:
        parts.append("")
        parts.append("required invariants (반드시 포함):")
        for kind, desc in defaults:
            parts.append(f"  - {kind}: {desc}")
    v = state.verification
    if v is not None and v.feedback is not None:
        parts.append("")
        parts.append(
            f"prior failure (target_node={v.feedback.target_node.value}, "
            f"mode={v.failure_mode.value}):"
        )
        parts.append(f"  hint: {v.feedback.actionable_hint}")
    return "\n".join(parts)


class DesignerLLM(Protocol):
    """designer 의 LLM dependency."""

    def generate(self, state: V1State) -> AlgorithmDesign: ...


class AnthropicDesignerLLM:
    """production impl — Sonnet + structured output."""

    def __init__(self, model: str = DESIGNER_MODEL) -> None:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatAnthropic(model_name=model, timeout=60, stop=None)
        prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM_PROMPT), ("user", "{user}")]
        )
        self._chain = prompt | llm.with_structured_output(AlgorithmDesign)

    def generate(self, state: V1State) -> AlgorithmDesign:
        result = self._chain.invoke({"user": _build_user_prompt(state)})
        if not isinstance(result, AlgorithmDesign):
            msg = (
                f"with_structured_output 가 {type(result).__name__} 반환 — "
                "AlgorithmDesign 기대"
            )
            raise TypeError(msg)
        return result


def make_designer_node(
    llm: DesignerLLM | None = None,
) -> Callable[[V1State], V1State]:
    resolved_llm: DesignerLLM = llm if llm is not None else AnthropicDesignerLLM()

    def node(state: V1State) -> V1State:
        if state.spec is None:
            msg = "designer node requires state.spec — architect must run first"
            raise ValueError(msg)
        design = resolved_llm.generate(state)
        return state.model_copy(update={"design": design})

    return node
