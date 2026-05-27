"""architect 노드 — target_algorithm → ProblemSpec (D안 PR-A3).

LLM: Opus 4.7. ``with_structured_output(ProblemSpec)`` 으로 Pydantic v2 model
직접 deserialize — v0 의 prose JSON parsing + R-coder-parse fallback 제거 (D안
H1 핵심).

retry 시 prev verification.feedback 의 actionable_hint + invariant_violations 를
prompt 에 structured 로 포함 → fix loop 결정론적 routing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ..schema import ProblemSpec
from ..state import V1State

ARCHITECT_MODEL = "claude-opus-4-7"
ARCHITECT_TEMPERATURE = 0.2


_SYSTEM_PROMPT = """\
당신은 algorithmic problem designer 이다. 주어진 target_algorithm 에 맞는
competitive programming problem 을 만든다.

다음 typed schema 를 정확히 따라 출력 (구조화된 tool call 로 반환됨):
- target_algorithm: 입력으로 받은 enum value 그대로
- title: 한 줄 문제 제목
- description: 사람용 자연어 설명 (한 문단)
- constraints: 변수의 ConstraintRange list (예: V[2..1000], E[1..10000])
- io_contract: input_format + output_format (간결, 한 줄씩)
- sample_testcases: 3~5 개. input_text + expected_output

Dijkstra 가 target 이면:
- input format: 첫 줄 "V E s t", 그 다음 E줄 "u v w" (0-indexed)
- output: 단일 정수 — d[s][t] (unreachable 이면 -1)
- non-negative weight 만 (Dijkstra 정의역)

Segment Tree (segtree) 가 target 이면:
- input format: 첫 줄 "N Q", 둘째 줄 "A_1 ... A_N" (1-indexed),
  그 다음 Q줄 각각 "U i v" (point update, 1-indexed) 또는 "Q l r" (range sum,
  1-indexed inclusive). **op keyword 는 반드시 대문자 'U' 또는 'Q' 한 글자**
  (숫자 코드 1/2 금지, 풀워드 update/query 금지).
- output: 각 "Q" op 마다 한 줄, 단일 정수.
- 음수 update 값 허용. variant = Range Sum + Point Update (Phase 2a).

LIS 가 target 이면:
- input format: 첫 줄 N, 둘째 줄 a_1 ... a_N
- output: 단일 정수 — strictly increasing LIS 길이

Two Sum (two_sum) 이 target 이면:
- input format: 첫 줄 "N T" (N=array 크기, T=target sum, 공백 구분),
  둘째 줄 "a_1 ... a_N" (1-indexed array, 공백 구분, 음수 허용).
- output: 1-indexed "i j" (i < j, a[i]+a[j]==T) 또는 "-1" (no valid pair).
  여러 valid pair 가 있으면 어느 하나만 출력해도 OK.

BFS (bfs) 가 target 이면:
- input format: 첫 줄 "V E s t" (V=노드 수, E=edge 수, s=source, t=target,
  모두 1-indexed), 그 다음 E줄 각각 "u v" (directed edge u→v, 1-indexed).
- output: 단일 정수 — s→t shortest edge count (unweighted), unreachable 시 "-1".
- variant: single-source single-target. directed graph. edge weight=1 가정.

Binary Search (binary_search) 가 target 이면:
- input format: 첫 줄 "N T" (N=array 크기, T=target value, 공백 구분),
  둘째 줄 "a_1 ... a_N" (sorted ascending, 1-indexed).
- output: 1-indexed index (a[idx]==T) 또는 "-1" (no match). 여러 valid idx 시
  어느 하나만 출력해도 OK.
- variant: classic exact match.

Union-Find (union_find) 가 target 이면:
- input format: 첫 줄 "N Q" (N=element 수, Q=op 갯수, 1-indexed),
  그 다음 Q줄 각각 "U x y" (union) 또는 "Q x y" (same-set query, 1-indexed).
  **op keyword 는 반드시 대문자 'U' 또는 'Q' 한 글자**.
- output: 각 "Q" op 마다 한 줄, 0 (다른 set) 또는 1 (같은 set).
- variant: classic same-set DSU.

Topological Sort (toposort) 가 target 이면:
- input format: 첫 줄 "N M" (N=노드 수, M=edge 수, 1-indexed),
  그 다음 M줄 각각 "u v" (directed edge u→v, 1<=u,v<=N, u != v).
- input 은 **반드시 DAG** (cycle 없음). cycle 있으면 verifier 가 skip 하여
  samples_engaged 가 떨어진다.
- output: N space-separated 정수 (한 줄 또는 여러 줄 모두 허용),
  1..N 의 valid topological order. 일반적으로 unique 하지 않으므로 어떤
  valid order 든 OK (예: pos[u] < pos[v] for all edges u→v).
- variant: classic DAG topological ordering.

0/1 Knapsack (knapsack) 가 target 이면:
- input format: 첫 줄 "N C" (N=item 갯수, C=capacity, 1-indexed),
  그 다음 N줄 각각 "w_i v_i" (weight, value 둘 다 non-negative 정수).
- output: 단일 정수 — capacity C 이하 최대 value 합.
- variant: classic 0/1 knapsack (each item 0 or 1 회 선택, no fractional).
- **중요**: sample N <= 15 (brute O(2^N) golden 의 안전 상한). N 이 너무 크면
  verifier 가 silent skip 하여 samples_engaged 가 떨어진다.

Comparison Sort (sort) 가 target 이면:
- input format: 첫 줄 "N" (배열 크기),
  둘째 줄 "a_1 a_2 ... a_N" (1-indexed, 정수, 중복/음수 허용).
- output: "b_1 b_2 ... b_N" — 입력의 ascending 정렬 (한 줄 권장,
  whitespace-tolerant).
- variant: classic comparison sort (Quicksort, Mergesort, Heapsort family).
  designer 가 algorithm 선택. non-strict ascending (중복 OK).

String Match (string_match) 가 target 이면:
- input format: 첫 줄 text (한 단어, ASCII printable, **공백 금지**),
  둘째 줄 pattern (한 단어, ASCII printable, **공백 금지**, non-empty).
- output: 단일 정수 — 1-indexed first occurrence index, 또는 "-1" (no match).
- variant: classic single-pattern substring search (KMP, Z-algorithm,
  Rabin-Karp family). designer 가 algorithm 선택.

Maximum Flow (max_flow) 가 target 이면:
- input format: 첫 줄 "V E s t" (V=노드 수, E=edge 수, s=source, t=sink,
  모두 1-indexed, s != t).
- 그 다음 E줄 각각 "u v c" (directed edge u→v, capacity c >= 0).
- output: 단일 정수 — s→t maximum flow.
- variant: classic single-source single-sink max flow (Ford-Fulkerson,
  Edmonds-Karp, Dinic family). designer 가 algorithm 선택.
- **중요**: sample V <= 12 (brute 2^V min-cut golden 의 안전 상한). V 가 너무
  크면 verifier 가 silent skip 하여 samples_engaged 가 떨어진다.

이전 시도가 실패해서 retry 면, feedback 의 actionable_hint 를 반영해 다른 spec.
"""


def _build_user_prompt(state: V1State) -> str:
    parts = [
        f"target_algorithm: {state.target_algorithm.value}",
        f"iteration: {state.iteration}",
    ]
    v = state.verification
    if v is not None and v.feedback is not None:
        fb = v.feedback
        parts.append("")
        parts.append(
            f"이전 시도가 실패함 (target_node={fb.target_node.value}, "
            f"failure_mode={v.failure_mode.value}):"
        )
        parts.append(f"  actionable_hint: {fb.actionable_hint}")
        parts.append(f"  blocking_signature: {fb.blocking_signature}")
        if v.invariant_violations:
            parts.append("  invariant_violations:")
            for iv in v.invariant_violations:
                parts.append(f"    - {iv.invariant_kind}: {iv.description}")
    return "\n".join(parts)


class ArchitectLLM(Protocol):
    """architect 의 LLM dependency. test 가 mock 주입."""

    def generate(self, state: V1State) -> ProblemSpec: ...


class AnthropicArchitectLLM:
    """production impl — langchain-anthropic with_structured_output.

    lazy import: test 는 langchain 없이 mock 만으로 가능.
    """

    def __init__(self, model: str = ARCHITECT_MODEL) -> None:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatAnthropic(model_name=model, timeout=60, stop=None)
        prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM_PROMPT), ("user", "{user}")]
        )
        self._chain = prompt | llm.with_structured_output(ProblemSpec)

    def generate(self, state: V1State) -> ProblemSpec:
        result = self._chain.invoke({"user": _build_user_prompt(state)})
        if not isinstance(result, ProblemSpec):
            msg = (
                f"with_structured_output 가 {type(result).__name__} 반환 — "
                "ProblemSpec 기대"
            )
            raise TypeError(msg)
        return result


def make_architect_node(
    llm: ArchitectLLM | None = None,
) -> Callable[[V1State], V1State]:
    """factory — graph build 시 호출. test 는 mock LLM 주입."""
    resolved_llm: ArchitectLLM = llm if llm is not None else AnthropicArchitectLLM()

    def node(state: V1State) -> V1State:
        spec = resolved_llm.generate(state)
        return state.model_copy(update={"spec": spec})

    return node
