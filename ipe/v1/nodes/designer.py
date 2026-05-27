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


LIS_DEFAULT_INVARIANTS: tuple[tuple[str, str], ...] = (
    ("non_negative_length", "출력 LIS 길이 >= 0"),
    ("length_le_input_size", "출력 LIS 길이 <= 입력 sequence 크기 N"),
    (
        "length_optimal",
        "patience sort O(N log N) golden 과 일치 (strictly increasing)",
    ),
)


SEGTREE_DEFAULT_INVARIANTS: tuple[tuple[str, str], ...] = (
    ("output_count_matches_queries", "출력 줄 수 == 입력의 Q query 갯수"),
    (
        "non_negative_sum_for_non_negative_input",
        "입력 a_i 및 update v 가 모두 >= 0 이면 모든 query 결과 >= 0",
    ),
    (
        "range_sum_optimal",
        "naive O(NQ) Python list 시뮬레이터 결과와 정확 일치",
    ),
    (
        "single_element_query_consistency",
        "l == r 일 때 결과 == 그 시점 array[l]",
    ),
)


TWO_SUM_DEFAULT_INVARIANTS: tuple[tuple[str, str], ...] = (
    ("output_format_valid", "출력이 '-1' 단독 또는 'i j' (두 정수) 형식"),
    ("indices_in_range_and_ordered", "i j 출력 시 1 <= i < j <= N"),
    ("sum_equals_target", "i j 출력 시 a[i] + a[j] == T"),
    (
        "existence_consistent",
        "brute O(N^2) golden 과 해 존재 여부 일치 ('-1' vs valid pair)",
    ),
)


BFS_DEFAULT_INVARIANTS: tuple[tuple[str, str], ...] = (
    ("non_negative_distance", "결과 거리 >= 0 또는 -1 (unreachable)"),
    ("source_zero", "s == t 일 때 결과 = 0"),
    (
        "reachability_consistent",
        "directed forward reachability 와 -1 여부 일치",
    ),
    (
        "distance_optimal",
        "Floyd-Warshall O(V^3) golden (edge weight=1) 과 일치",
    ),
)


BINARY_SEARCH_DEFAULT_INVARIANTS: tuple[tuple[str, str], ...] = (
    ("output_format_valid", "출력이 단일 정수 (-1 또는 1-indexed positive)"),
    ("index_in_range", "-1 또는 1 <= idx <= N"),
    (
        "value_matches_target_when_found",
        "idx > 0 일 때 a[idx] == T",
    ),
    (
        "existence_consistent",
        "linear scan golden 의 발견 여부와 일치 ('-1' vs valid idx)",
    ),
)


UNION_FIND_DEFAULT_INVARIANTS: tuple[tuple[str, str], ...] = (
    ("output_count_matches_queries", "출력 줄 수 == 입력의 Q op 갯수"),
    ("binary_output_for_queries", "모든 출력 ∈ {0, 1}"),
    (
        "same_set_correctness",
        "BFS over union edges (naive O(N) per query) golden 과 일치",
    ),
    (
        "self_query_returns_one",
        "Q x x (self-query) 는 항상 1",
    ),
)


TOPOSORT_DEFAULT_INVARIANTS: tuple[tuple[str, str], ...] = (
    ("output_length_matches_n", "출력 정수 갯수 == N"),
    ("output_is_permutation", "출력 ∈ permutation of 1..N (중복/범위초과 없음)"),
    (
        "edges_respect_order",
        "모든 edge u→v 에 대해 pos[u] < pos[v]",
    ),
    (
        "dag_input_via_kahn",
        "input 자체가 DAG (Kahn O(V+E) cross-check, cycle 이면 verifier skip)",
    ),
)


KNAPSACK_DEFAULT_INVARIANTS: tuple[tuple[str, str], ...] = (
    ("output_is_single_int", "출력이 단일 정수"),
    ("value_non_negative", "출력 >= 0"),
    ("value_within_total_bound", "0 <= 출력 <= sum(v_i)"),
    (
        "value_optimal_via_brute",
        "brute O(2^N) subset enum golden 과 일치 (sample N <= 15)",
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

target_algorithm = "lis" 면 다음 3 invariants 를 반드시 포함:
- non_negative_length
- length_le_input_size
- length_optimal

target_algorithm = "two_sum" 면 다음 4 invariants 를 반드시 포함:
- output_format_valid
- indices_in_range_and_ordered
- sum_equals_target
- existence_consistent

two_sum 의 input/output format 은 다음 표준을 **반드시** 따른다:
- 첫 줄: "N T" (N=array 크기, T=target sum, 공백 구분)
- 둘째 줄: a_1 a_2 ... a_N (1-indexed array, 공백 구분, 음수 허용)
- output: 1-indexed "i j" (i < j, a[i]+a[j]==T) 또는 "-1" (no valid pair)
- 출력은 한 줄. 여러 valid pair 가 있으면 어느 하나만 출력해도 OK.

target_algorithm = "bfs" 면 다음 4 invariants 를 반드시 포함:
- non_negative_distance
- source_zero
- reachability_consistent
- distance_optimal

bfs 의 input/output format 은 다음 표준을 **반드시** 따른다:
- 첫 줄: "V E s t" (V=노드 수, E=edge 수, s=source, t=target. 모두 1-indexed)
- 그 다음 E줄: 각 줄 "u v" (directed edge u→v, 1-indexed, 1<=u,v<=V)
- output: 단일 정수 — s→t shortest edge count (unweighted), unreachable 시 "-1"
- variant: single-source single-target. directed graph. edge weight=1 가정.

target_algorithm = "binary_search" 면 다음 4 invariants 를 반드시 포함:
- output_format_valid
- index_in_range
- value_matches_target_when_found
- existence_consistent

binary_search 의 input/output format 은 다음 표준을 **반드시** 따른다:
- 첫 줄: "N T" (N=array 크기, T=target value, 공백 구분)
- 둘째 줄: a_1 a_2 ... a_N (sorted ascending, 1-indexed)
- output: 1-indexed index (a[idx]==T, 여러 valid idx 시 어느 하나 OK) 또는
  "-1" (no match)
- variant: classic exact match (lower/upper bound 는 미지원).

target_algorithm = "union_find" 면 다음 4 invariants 를 반드시 포함:
- output_count_matches_queries
- binary_output_for_queries
- same_set_correctness
- self_query_returns_one

union_find 의 input/output format 은 다음 표준을 **반드시** 따른다:
- 첫 줄: "N Q" (N=element 수, Q=op 갯수, 공백 구분)
- 그 다음 Q 줄: 각 줄 op. **op keyword 대문자 'U' 또는 'Q' 한 글자**:
  - "U x y": union x, y (1-indexed, no output)
  - "Q x y": same-set query, 출력 0 또는 1 (1-indexed)
- output: 각 "Q" op 마다 한 줄, 0 또는 1.
- variant: classic same-set DSU.

target_algorithm = "toposort" 면 다음 4 invariants 를 반드시 포함:
- output_length_matches_n
- output_is_permutation
- edges_respect_order
- dag_input_via_kahn

toposort 의 input/output format 은 다음 표준을 **반드시** 따른다:
- 첫 줄: "N M" (N=노드 수, M=edge 수, 공백 구분, 1-indexed)
- 그 다음 M 줄: 각 줄 "u v" (directed edge u→v, 1<=u,v<=N, u != v)
- output: N space-separated 정수 (한 줄 또는 여러 줄), 1..N 의 valid topo order
- variant: classic DAG topological ordering. input 은 cycle 없는 DAG 가정.
  topo order 는 일반적으로 unique 하지 않으므로 어떤 valid order 든 OK.

target_algorithm = "knapsack" 면 다음 4 invariants 를 반드시 포함:
- output_is_single_int
- value_non_negative
- value_within_total_bound
- value_optimal_via_brute

knapsack 의 input/output format 은 다음 표준을 **반드시** 따른다:
- 첫 줄: "N C" (N=item 갯수, C=capacity, 공백 구분, 1-indexed items)
- 그 다음 N 줄: 각 줄 "w_i v_i" (weight, value 둘 다 정수, 음수 금지)
- output: 단일 정수 — capacity C 이하 최대 value 합
- variant: classic 0/1 knapsack (each item 0 or 1 회 선택, no fractional).
- **important: sample N <= 15** (brute O(2^N) golden 의 안전 상한; verifier 가
  N > 22 면 silent skip)

target_algorithm = "segtree" 면 다음 4 invariants 를 반드시 포함:
- output_count_matches_queries
- non_negative_sum_for_non_negative_input
- range_sum_optimal
- single_element_query_consistency

segtree 의 input/output format 은 다음 표준을 **반드시** 따른다 (PR-B2.1 format
정합 — verifier parse 와 1:1 매칭 의무):
- 첫 줄: "N Q" (N=array 크기, Q=op 갯수, 공백 구분)
- 둘째 줄: A_1 A_2 ... A_N (1-indexed array, 공백 구분)
- 그 다음 Q 줄: 각 줄에 op. **op keyword 는 반드시 대문자 'U' 또는 'Q' 한 글자**:
  - "U i v" : A[i] = v (point update, 1<=i<=N, v 는 음수 허용)
  - "Q l r" : sum(A[l..r]) 출력 (inclusive, 1<=l<=r<=N)
- **금지**: 숫자 코드 (1, 2 등), 풀워드 (update, query), 다른 약자.
output: 각 "Q" op 마다 한 줄, 단일 정수.

architect 가 sample_testcases 만들 때 위 format 을 엄격히 따라야 verifier
engagement (samples_engaged > 0) 가 보장됨.

위 kind 들은 verifier dispatch key 이므로 정확한 spelling 필수.

- data_structures: 사용할 자료구조 list (예: ["priority_queue", "adjacency_list"])
"""


def _default_invariants_for(target_algorithm: str) -> list[tuple[str, str]]:
    if target_algorithm == "dijkstra":
        return list(DIJKSTRA_DEFAULT_INVARIANTS)
    if target_algorithm == "lis":
        return list(LIS_DEFAULT_INVARIANTS)
    if target_algorithm == "segtree":
        return list(SEGTREE_DEFAULT_INVARIANTS)
    if target_algorithm == "two_sum":
        return list(TWO_SUM_DEFAULT_INVARIANTS)
    if target_algorithm == "bfs":
        return list(BFS_DEFAULT_INVARIANTS)
    if target_algorithm == "binary_search":
        return list(BINARY_SEARCH_DEFAULT_INVARIANTS)
    if target_algorithm == "union_find":
        return list(UNION_FIND_DEFAULT_INVARIANTS)
    if target_algorithm == "toposort":
        return list(TOPOSORT_DEFAULT_INVARIANTS)
    if target_algorithm == "knapsack":
        return list(KNAPSACK_DEFAULT_INVARIANTS)
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
