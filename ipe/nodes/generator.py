"""Generator node — Codeforces Polygon 패턴 시드 기반 입력 생성기 작성자.

스펙: PROJECT_SPEC.md §4.4 (The Generator), ARCHITECTURE.md §3.8

- 입력: problem_description, constraints, solution_code (+ feedback_message)
- 출력: ``generators: list[{name, category, description, code, seeds}]``
- LLM이 입력 데이터 자체를 출력하지 않고 시드 받는 Python 스크립트를 작성
  → 결정론적 + 토큰 비용 절감

스크립트 형태 (LLM이 작성)::

    import sys, random
    seed = int(sys.argv[1])
    random.seed(seed)
    n = random.randint(50, 100)
    print(n)
    print(' '.join(str(random.randint(1, 1000)) for _ in range(n)))

3개 미만 반환 시 self-loop (``last_failed_node='generator'``).
"""

from __future__ import annotations

import re
from typing import Any

from ipe.llm import GENERATOR_MODEL, get_chat
from ipe.nodes._history import build_history_section
from ipe.observability import LLMCallTracker
from ipe.state import LLMCallRecord, ProblemState

DEFAULT_SEEDS_PER_GENERATOR: tuple[int, ...] = (1, 2, 3, 4, 5)
MIN_GENERATORS = 3
MAX_GENERATORS = 5

SYSTEM_PROMPT = """You are The Generator — a stress-test input writer.

Given a problem and golden solution, write 3–5 Python scripts that take a
single integer seed (``sys.argv[1]``) and produce stdin text deterministically.

Output format — repeat 3–5 blocks:

NAME: gen_random_small
CATEGORY: RANDOM_SMALL
DESCRIPTION: <one short line>
```python
import sys, random
seed = int(sys.argv[1])
random.seed(seed)
n = random.randint(50, 100)
print(n)
print(' '.join(str(random.randint(1, 1000)) for _ in range(n)))
```

Categories:
- RANDOM_SMALL: small random instances (N ≈ 100, output ≤ 10 KB)
- RANDOM_MEDIUM: medium random (N ≈ 10,000, output ≤ 200 KB)
- MAX_STRESS: maximum constraint values (worst-case stress, output ≤ 1.5 MB)
- SPECIAL_STRUCTURE: structured cases (paths, complete graphs, sorted, etc.)

Each script MUST:
- Read seed from ``sys.argv[1]`` and call ``random.seed(seed)``
- Print stdin text matching the problem's input format
- Respect constraints (N within bounds, values within ranges)
- Run in <2 seconds and **print < 2 MB** (hard cap — over this is rejected)
- Be self-contained (only stdlib imports)

**Output size discipline (R10)**:
For MAX_STRESS, prefer N at constraint maximum but use compact value ranges
when needed to stay under 2 MB. Example: if N_max = 200000, integer values
fitting in int32 (~10 chars each) yield ~2 MB — keep values smaller (e.g.
1..10^6 instead of 1..10^9) when targeting MAX_STRESS, OR reduce N below
maximum. Oversize generators are rejected and you must rewrite.

**Multi-section input size budgeting (R3 — CRITICAL for problems with
multiple input dimensions like Segment Tree / Range Query / Online algorithms)**:

Many problems have TWO independent size dimensions in input:
- Array size N AND query count M (Segment Tree, Range Sum, RMQ, ...)
- Vertex count V AND edge count E (sparse graphs)
- String length L AND query count Q (string algorithms)

For these problems, the **TOTAL output size = sum of all dimensions**.
Calculate output size budget BEFORE choosing dimensions:

  total_bytes ≈ N * avg_value_chars        # array
              + M * avg_query_chars        # queries (e.g. "U 100000 -999999999" ≈ 20 chars)
              + ...

Example (Segment Tree, N + M dual input):
- N=200000 integers (10 chars each) ≈ 2 MB ← already exceeds 2MB cap alone
- M=200000 queries ("U p v" or "Q l r", 15-20 chars each) ≈ 3-4 MB
- TOTAL ≈ 5-6 MB → REJECTED

For dual-dimension problems with N_max + M_max stress:
- Either reduce both dimensions (e.g. N = M = 50000 instead of 200000)
- OR use compact value ranges (e.g. values 1..1000 instead of 1..10^9)
- OR fix one dimension to max and reduce the other (N=200000 with M=10000)

**Always estimate total output bytes before writing the generator code.**
"""

USER_TEMPLATE = """## Problem

{problem_description}

## Constraints

{constraints}

## Golden Solution

```
{solution_code}
```

Generate 3–5 input generator scripts following the format above.
"""

FEEDBACK_SUFFIX = """

## Previous Failure Feedback

{feedback}

이전 시도와 다른 카테고리/접근법을 사용하라 (REVIEW W4: oscillation 방지).
"""

# 매치: NAME / CATEGORY / DESCRIPTION 헤더 + ```python fence```
_BLOCK_RE = re.compile(
    r"NAME:\s*(?P<name>\S+)\s*\n"
    r"CATEGORY:\s*(?P<category>\S+)\s*\n"
    r"DESCRIPTION:\s*(?P<description>[^\n]*)\n"
    r"```(?:python)?\s*\n(?P<code>.*?)```",
    re.DOTALL,
)


def _route_back(
    state: ProblemState, calls: list[LLMCallRecord], reason: str
) -> ProblemState:
    """generator self-loop으로 라우팅."""
    return {
        **state,
        "llm_calls": calls,
        "feedback_message": reason,
        "last_failed_node": "generator",
    }


def _parse(text: str) -> list[dict[str, Any]]:
    """LLM 응답에서 generator 블록을 추출.

    각 entry는 ``{name, category, description, code, seeds}`` 형식.
    seeds는 ``DEFAULT_SEEDS_PER_GENERATOR``의 복사본 (mutation 방지).
    """
    out: list[dict[str, Any]] = []
    for m in _BLOCK_RE.finditer(text):
        out.append({
            "name": m.group("name").strip(),
            "category": m.group("category").strip(),
            "description": m.group("description").strip(),
            "code": m.group("code"),
            "seeds": list(DEFAULT_SEEDS_PER_GENERATOR),
        })
    return out


def run(
    state: ProblemState,
    *,
    tracker: LLMCallTracker,
) -> ProblemState:
    """Generator 노드 — 시드 기반 Python 스크립트 3~5개 생성."""
    chat = get_chat(GENERATOR_MODEL, max_tokens=4096)
    user = USER_TEMPLATE.format(
        problem_description=state.get("problem_description", ""),
        constraints=state.get("constraints", ""),
        solution_code=state.get("solution_code", ""),
    )
    feedback = state.get("feedback_message")
    if feedback:
        user += FEEDBACK_SUFFIX.format(feedback=feedback)
    user += build_history_section(state, current_node="generator")

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    calls: list[LLMCallRecord] = list(state.get("llm_calls") or [])
    resp = tracker.invoke(chat, messages, node="generator", state_calls=calls)
    text = str(resp.content)

    generators = _parse(text)

    if len(generators) < MIN_GENERATORS:
        return _route_back(
            state,
            calls,
            f"generator: only {len(generators)} parsed, need >= {MIN_GENERATORS}",
        )

    return {
        **state,
        "llm_calls": calls,
        "generators": generators[:MAX_GENERATORS],
        "feedback_message": None,
        "last_failed_node": None,
    }
