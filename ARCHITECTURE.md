# IPE 프로젝트 코드 구조 가이드

> 이 문서는 Python에 익숙하지 않은 독자를 위해, 프로젝트의 **아키텍처**와 함께 코드에 등장하는 **Python 문법/관용구**를 함께 설명합니다.

---

## 0. 한눈에 보는 그림

```
사용자 CLI (main.py)
        │
        ▼
   build_graph()  ──┐
        │            │  LangGraph가 노드 사이의
        ▼            │  '상태(state)' 전달과 라우팅을 담당
 ┌──────────────┐    │
 │  Architect   │  ◄ ┘
 └──────┬───────┘
        ▼ (problem_title, description, constraints, sample_testcases)
 ┌──────────────┐
 │    Coder     │
 └──────┬───────┘
        ▼ (solution_code)
 ┌──────────────┐
 │   Auditor    │
 └──────┬───────┘
        ▼ (adversarial_inputs : 8~15개의 작은 엣지케이스)
 ┌──────────────┐
 │  Generator   │
 └──────┬───────┘
        ▼ (generators : 시드 받는 Python 스크립트 3~5개)
 ┌──────────────┐
 │   Executor   │  Phase A → B → C
 └──────┬───────┘
        ▼ 조건부 분기 (route_after_executor)
   ┌────┴─────┐
   │ success  │── Evaluator → END (산출물 저장)
   │ coder    │── 다시 Coder로
   │ auditor  │── 다시 Auditor로
   │ generator│── 다시 Generator로
   │ architect│── 다시 Architect로
   │ halt     │── max_iter 초과 시 종료
   └──────────┘
        ▼ (검증 통과 시)
 ┌──────────────┐
 │  Evaluator   │  난이도 사후 측정
 └──────┬───────┘
        ▼ (difficulty_label, difficulty_reasoning, difficulty_factors)
       END
```

핵심 아이디어:
- **6개 LLM/도구 노드**가 단일 `ProblemState`(딕셔너리)를 주거니 받거니 하면서 점진적으로 채운다.
- 노드는 **순수 함수**처럼 `(state) → state` 시그니처를 갖는다. LangGraph가 이 함수들을 호출 순서/조건에 맞게 묶어준다.
- LLM 출력 + **격리 환경(sandbox) 안의** `subprocess` 실행이 결합된 **에이전트 + 결정론적 검증** 하이브리드.
- **난이도는 사전 지정이 아닌, 검증 완료 후 Evaluator가 사후 측정**한다.
- **Resumable**: LangGraph `SqliteSaver`로 노드 단위 상태 지속화 → 어느 단계에서 죽어도 `--resume <run_id>`로 이어서 실행.
- **Observable**: 모든 LLM 호출은 `outputs/<run_id>/llm_traces/`에 raw로 저장되고 `state["llm_calls"]`에 토큰·비용이 누적됨. `--replay`로 캐시 재생 가능.
- **Bounded**: 글로벌 `max_iter` (안전망) + per-node retry budget (정밀 제어) + `max_cost_usd` (비용 가드). 셋 중 하나라도 도달 시 halt.

---

## 1. 데이터 흐름

### 1.1 한 사이클 동안 채워지는 필드들

```
Architect 출력  →  state["problem_title"], state["problem_description"],
                  state["constraints"], state["sample_testcases"]

Coder 출력      →  state["solution_code"]

Auditor 출력    →  state["adversarial_inputs"]

Generator 출력  →  state["generators"]
                  (각 generator: {name, category, code, seeds, description})

Executor 출력   →  state["execution_results"], state["testcases"],
                  state["iteration_count"], state["final_status"],
                  state["last_failed_node"], state["feedback_message"]

Evaluator 출력  →  state["difficulty_label"], state["difficulty_reasoning"],
                  state["difficulty_factors"]
```

### 1.2 실패 시 피드백 루프

`Executor`가 검증 후 어떤 노드로 다시 보낼지 결정합니다. 이 신호는 두 필드로 표현됩니다:

- `state["last_failed_node"]` — 어디로 돌아갈지 (`"coder"`, `"auditor"`, `"architect"`, `"generator"` 중 하나, 또는 `None`)
- `state["feedback_message"]` — 실패 사유를 자연어로 담은 문자열. 다음 호출 시 해당 노드의 프롬프트 끝에 붙여 LLM이 자기 출력을 수정할 수 있도록 함.

`state["iteration_count"]`가 `max_iter`(기본 5)에 도달하면 `halt` 노드로 가서 `final_status="max_iterations"`로 종료.

---

## 2. 파일 구조

```
cc_workspace/
├─ main.py                  # CLI 진입점 (--resume / --replay / --sandbox / --max-cost-usd)
├─ requirements.txt          # langgraph, langchain-anthropic, anthropic, python-dotenv
├─ .env.example             # ANTHROPIC_API_KEY=
├─ .gitignore
├─ README.md                # 빠른 시작
├─ project_spec.md          # 원본 요구 명세
├─ ARCHITECTURE.md          # (이 문서)
│
├─ ipe/                     # 메인 패키지
│  ├─ __init__.py           # 빈 파일 — Python에 "이 디렉토리는 패키지다"라고 알림
│  ├─ state.py              # ProblemState / ConstraintSpec / IterationRecord / LLMCallRecord
│  ├─ llm.py                # Claude 클라이언트 + JSON 파서 + LLMCallTracker (cost/trace 자동 기록)
│  ├─ graph.py              # LangGraph 빌더 (SqliteSaver checkpointer + 라우터)
│  ├─ io.py                 # 산출물 저장 (Polygon-style)
│  ├─ observability.py      # 구조적 로깅, 메트릭, (옵션) LangSmith/OTel hook
│  ├─ sandbox/              # 코드 실행 격리 레이어
│  │  ├─ __init__.py
│  │  ├─ runner.py          # SandboxedRunner abstract base
│  │  ├─ docker_runner.py   # T1: Docker 컨테이너
│  │  ├─ nsjail_runner.py   # T2: nsjail/firejail/bubblewrap
│  │  └─ rlimit_runner.py   # T3: setrlimit only fallback
│  ├─ calibration/
│  │  └─ anchors.json       # Difficulty Evaluator용 백준 reference 샘플
│  └─ nodes/
│     ├─ __init__.py
│     ├─ architect.py       # constraints_structured 출력 강제
│     ├─ coder.py
│     ├─ auditor.py         # syntactic validator는 executor에서
│     ├─ generator.py
│     ├─ executor.py        # SandboxedRunner + ThreadPoolExecutor 병렬
│     └─ evaluator.py       # calibration anchors 동봉
│
├─ outputs/                 # 생성된 문제 산출물 (gitignore)
│  ├─ index.jsonl           # (P2 - Future) 중복/유사 검출용 인덱스 (algo, title, embedding)
│  └─ <run_id>/             # uuid 기반 (timestamp_algo는 별칭 심볼릭 링크)
│     ├─ problem.json       # DB 인서트 가능한 정형 데이터
│     ├─ problem.md         # 사람이 읽는 형태
│     ├─ solution.py 또는 Solution.java
│     ├─ generators/<name>.py
│     ├─ tests/
│     │  ├─ 01.in / 01.out / ... / NN.in / NN.out
│     │  └─ manifest.json
│     ├─ llm_traces/        # 모든 LLM 호출의 raw 입출력 (재현/디버깅)
│     │  └─ <seq>_<node>.json   # {seq, node, model, system, user, response, tokens, cost_usd, ts}
│     └─ checkpoint.db      # LangGraph SqliteSaver — resume 가능
│
└─ workdir/                 # Executor 임시 컴파일/실행 (gitignore, sandbox 외부 호스트 작업영역)
```

**Python 패키지 메모:** `__init__.py` 파일이 들어있는 디렉토리는 Python에서 "패키지"가 됩니다. 이 파일이 비어있어도 됩니다. `from ipe.nodes import architect` 같은 import가 가능해지는 이유입니다.

---

## 3. 모듈별 상세 설명

### 3.1 `main.py` — CLI 진입점

```python
import argparse
from pathlib import Path
from dotenv import load_dotenv
from ipe.graph import DEFAULT_MAX_ITER, build_graph
from ipe.io import save_result


def main() -> None:
    load_dotenv()                                          # ① .env 파일 로드
    parser = argparse.ArgumentParser(...)                  # ② CLI 인자 정의
    parser.add_argument("--algorithm", required=True, ...)
    # --difficulty 인자는 없음: 난이도는 Evaluator가 사후 측정
    parser.add_argument("--language", choices=["python", "java"], default="python")
    parser.add_argument("--max-iter", type=int, default=DEFAULT_MAX_ITER)
    args = parser.parse_args()

    initial_state = {                                      # ③ 초기 상태 dict
        "target_algorithm": args.algorithm,
        ...
    }

    graph = build_graph(max_iter=args.max_iter)            # ④ 그래프 빌드
    final_state = graph.invoke(initial_state, config={...}) # ⑤ 실행
    folder = save_result(final_state, outputs_root)         # ⑥ 결과 저장


if __name__ == "__main__":                                 # ⑦
    main()
```

**Python 문법 노트:**

| 패턴 | 의미 |
|---|---|
| `def main() -> None:` | 함수 선언. `-> None`은 "반환값이 없다"는 타입 힌트. Python은 동적 타입이지만 타입 힌트는 IDE/도구가 활용. |
| `from X import Y` | `X`라는 모듈에서 `Y` 심볼만 골라 가져옴. (Java의 `import x.Y;`와 비슷.) |
| `args.algorithm` | `argparse`가 동적으로 만든 객체의 속성 접근. `--algorithm` → `args.algorithm` (`-`가 `_`로 변환). |
| `if __name__ == "__main__":` | "이 파일이 직접 실행될 때만 main() 호출. import 될 때는 호출하지 마라." Python의 표준 idiom. |
| f-string `f"..."` | 문자열 안에 `{변수}` 직접 삽입. `f"{x!r}"`는 `repr(x)` 호출 (디버깅에 유용 — 따옴표/이스케이프 보존). |

**`load_dotenv()`의 역할:** 같은 디렉토리의 `.env` 파일을 읽어서 그 안의 `KEY=value` 쌍을 환경변수로 등록합니다. `langchain-anthropic`은 자동으로 `os.environ["ANTHROPIC_API_KEY"]`를 찾습니다.

**`graph.invoke(initial_state, config={...})`:** LangGraph의 표준 호출 패턴. `recursion_limit`은 노드를 최대 몇 번 통과할 수 있는지 한도를 지정 (무한루프 안전장치).

---

### 3.2 `ipe/state.py` — 공유 상태 타입

```python
from typing import TypedDict, List, Dict, Optional


class ProblemState(TypedDict, total=False):
    target_algorithm: str
    iteration_count: int

    problem_title: str
    problem_description: str
    constraints: str

    solution_code: str
    target_language: str

    sample_testcases: List[Dict]
    adversarial_inputs: List[Dict]
    generators: List[Dict]
    testcases: List[Dict]

    execution_results: List[Dict]
    feedback_message: Optional[str]
    last_failed_node: Optional[str]
    final_status: Optional[str]
    max_iter: int

    # Difficulty Evaluator Output (검증 완료 후 사후 측정)
    difficulty_label: Optional[str]       # ex: "Gold 3", "Silver 1"
    difficulty_reasoning: Optional[str]   # 난이도 판정 근거
    difficulty_factors: Optional[Dict]    # 세부 평가 요소
```

**Python 문법 핵심:**

- **`TypedDict`**: 일반 `dict`인데 키와 타입을 명시적으로 선언한 것. 런타임에는 그냥 dict처럼 동작하지만, 타입 체커(mypy 등)가 잘못된 키 접근을 잡아냅니다.
  - Java로 비유하면 "필드만 있는 record 클래스" 비슷한 역할이지만, 실제로는 `{"key": value}` dict.
  - `state["problem_title"]` 처럼 접근하면 됩니다.
- **`total=False`**: "모든 필드가 있어야 하는 건 아님". 처음에는 `target_algorithm`만 채우고, 노드를 거치면서 점점 다른 필드가 채워지므로 부분적으로 비어있는 상태가 정상.
- **`Optional[str]`**: `str` 또는 `None` 둘 다 허용. `Union[str, None]`의 줄임표현.
- **`Optional[Dict]`**: `Dict` 또는 `None`. Evaluator가 아직 실행되지 않았을 때는 `None`.
- **`target_difficulty` 필드는 없음**: 난이도는 입력이 아닌 Evaluator의 사후 출력.

**왜 dict로 상태를 관리하나:** LangGraph가 채택한 패턴으로, 노드는 이 dict를 받아 *부분 업데이트된 새 dict*를 반환하면 LangGraph가 자동으로 머지해줍니다.

---

### 3.3 `ipe/llm.py` — Claude 호출과 JSON 파싱

#### 3.3.0 모델명 ↔ API ID 표준 매핑 (SSOT)

> **이 표가 IPE 전체에서 사용하는 모델 식별자의 단일 진실원이다.** 다른 문서(`PROJECT_SPEC.md` 등)에서 마케팅명을 사용하더라도 코드는 반드시 API ID를 사용해야 한다 (REVIEW_REPORT M2).

| 마케팅명 (사람용) | API ID (코드용) | 용도 | 주요 노드 |
|---|---|---|---|
| Claude Opus 4.7 | `claude-opus-4-7` | 최고 추론 능력 | Architect, Auditor, Generator, Evaluator |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | 코드 생성 특화 | Coder (1차 시도) |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | 저비용·고속 | (옵션) escalation 1단계 |

* SPEC/ARCH 본문에서 모델을 언급할 때는 마케팅명을 사용해도 되지만, **모든 코드 예시·configuration·trace에는 API ID만 사용**.
* 가격(`PRICING` dict, §3.12)은 API ID를 키로 한다.
* 모델 추가/변경 시 본 표 → `ipe/llm.py` 상수 → `ipe/observability.py:PRICING` 순서로 업데이트.

#### 3.3.1 `get_chat()` — 동적 모델 선택

```python
ARCHITECT_MODEL = "claude-opus-4-7"
CODER_MODEL = "claude-sonnet-4-6"
AUDITOR_MODEL = "claude-opus-4-7"

_TEMPERATURE_CAPABLE = {CODER_MODEL}    # set 자료형 (중괄호 + 콤마)


def get_chat(model: str, temperature: float | None = None, max_tokens: int = 4096) -> ChatAnthropic:
    kwargs: dict = {"model": model, "max_tokens": max_tokens}
    if temperature is not None and model in _TEMPERATURE_CAPABLE:
        kwargs["temperature"] = temperature
    return ChatAnthropic(**kwargs)
```

**Python 문법 노트:**

| 패턴 | 의미 |
|---|---|
| `temperature: float \| None = None` | "float 또는 None, 기본값 None". `\|`는 Python 3.10+의 union 표기. |
| `_TEMPERATURE_CAPABLE = {CODER_MODEL}` | 앞에 `_`가 붙은 이름은 "이 모듈 내부용, 외부에서 쓰지 마"라는 컨벤션 (privacy 강제 아님). |
| `model in _TEMPERATURE_CAPABLE` | set 멤버십 체크 (Java의 `set.contains(model)`). |
| `**kwargs` | dict를 함수 호출 시 **키워드 인자로 펼치기** (unpack). `ChatAnthropic(model=..., max_tokens=...)` 와 동일. 매우 자주 쓰는 idiom. |

**왜 이렇게 했나:** Claude Opus 4.7은 `temperature` 인자를 거부합니다. 그래서 모델이 그걸 지원하는지 확인하고 동적으로 인자를 구성. `**kwargs`를 쓰면 분기마다 함수 호출문을 따로 쓰지 않아도 됩니다.

#### 3.3.2 `parse_json_block(text)` — JSON 추출

LLM 응답 안에서 JSON을 안전하게 빼냅니다. 우선순위:
1. ```` ```json ... ``` ```` 펜스 안의 JSON
2. 응답에서 가장 바깥 `{...}` 또는 `[...]`

#### 3.3.3 `parse_json_array_field(text, field_name)` — 절단 복구 파서

LLM 출력이 `max_tokens` 한계로 잘려서 JSON이 미완성일 때, 완성된 entry까지만 살려냅니다.

```python
def _walk_complete_objects(text: str, start_idx: int) -> list:
    i = text.find("[", start_idx)
    ...
    while i < len(text):
        # 공백/콤마 건너뛰기
        while i < len(text) and text[i] in " \t\n\r,":
            i += 1
        ...
        # 중괄호 깊이를 세면서 한 객체의 닫는 } 찾기
        # 문자열 안에 있는 { } 는 무시 (in_str 플래그)
        # 이스케이프 \" 도 처리 (esc 플래그)
```

**Python 문법 노트:**
- `text.find("[", start_idx)` — 문자열에서 `[` 의 위치를 `start_idx`부터 찾기. 없으면 `-1`.
- `text[i : j+1]` — **슬라이싱**. `i` 인덱스부터 `j` 인덱스까지(끝 미포함) 부분 문자열. `j+1`을 끝점으로 줘야 `j` 위치 문자가 포함됨.
- `out: list = []` — 빈 리스트. 타입 힌트는 명시적으로 `list`라고 선언.

이 함수는 **상태기계(state machine)** 패턴으로 문자열을 한 글자씩 스캔하며 JSON 구조를 추적합니다. Python에 표준 "스트리밍 JSON 파서"가 없어서 직접 구현한 것입니다.

---

### 3.4 `ipe/graph.py` — LangGraph 빌더

```python
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver
from ipe.nodes import architect, auditor, coder, evaluator, executor, generator
from ipe.state import ProblemState


DEFAULT_MAX_ITER = 7  # REVIEW Q5: 5→7 (노드 합 10 - 3, 글로벌이 노드별 budget 무력화 방지)
DEFAULT_NODE_BUDGET = {"architect": 2, "coder": 4, "auditor": 2, "generator": 2}  # coder 3→4
DEFAULT_MAX_COST_USD = 5.0


def _budget_remaining(state: ProblemState, node: str) -> int:
    budget = state.get("node_retry_budget") or dict(DEFAULT_NODE_BUDGET)
    return budget.get(node, 0)


def _cost_so_far(state: ProblemState) -> float:
    return sum(c.get("cost_usd", 0.0) for c in state.get("llm_calls", []))


# ────────────────────────────────────────────────────────────────────
# Implementation note (P7 + P9 반영, 2026-05-09):
#
# 아래 ``route_after_executor`` 는 ARCH spec-level intent. 실제 ``ipe/graph.py`` 는:
#  - P7: ``_decision`` 노드 + ``_route_after_decision`` 분기 함수 분리.
#        executor → decision → conditional_edges → {nodes / END}.
#        halt 노드 제거 — final_status는 ``_decision`` 안에서 직접 set.
#  - P9: success 분기에 ``evaluator`` 노드 추가 (난이도 측정 후 END).
#  - drift: 우선순위 cost > **success preserve** > max_iter > budget
#           (CHANGES §5는 cost > budget > max_iter — 메시지 차이만 있는 minor).
#
# 자세한 코드는 ``ipe/graph.py`` 참조 (post-p12 backlog 항목 추적 중).
# ────────────────────────────────────────────────────────────────────


def route_after_executor(state: ProblemState) -> str:
    # 1) success
    if state.get("final_status") == "success":
        return "evaluator"

    # 2) cost guard (P1)
    max_cost = state.get("max_cost_usd") or DEFAULT_MAX_COST_USD
    if _cost_so_far(state) > max_cost:
        return "halt"   # final_status="cost_exceeded"는 halt 노드에서 set

    # 3) global iteration safety net
    if state.get("iteration_count", 0) >= state.get("max_iter", DEFAULT_MAX_ITER):
        return "halt"   # final_status="max_iterations"

    # 4) per-node budget
    failed = state.get("last_failed_node")
    if failed in ("architect", "coder", "auditor", "generator"):
        if _budget_remaining(state, failed) <= 0:
            return "halt"   # final_status="budget_exhausted"
        return failed

    return "halt"


def build_graph(
    max_iter: int = DEFAULT_MAX_ITER,
    node_budget: dict | None = None,
    max_cost_usd: float = DEFAULT_MAX_COST_USD,
    checkpoint_db: str | None = None,        # outputs/<run_id>/checkpoint.db
    parallel_fanout: bool = False,           # P1: Auditor || Generator
):
    g = StateGraph(ProblemState)
    g.add_node("architect", architect.run)
    g.add_node("coder", coder.run)
    g.add_node("auditor", auditor.run)
    g.add_node("generator", generator.run)
    g.add_node("executor", executor.run)
    g.add_node("evaluator", evaluator.run)
    g.add_node("halt", _halt)

    g.add_edge(START, "architect")
    g.add_edge("architect", "coder")

    if parallel_fanout:
        # Coder 출력 후 Auditor와 Generator를 병렬로 실행 → 둘 다 끝나면 Executor로.
        # LangGraph의 fan-out은 동일 source에서 여러 add_edge로 표현, fan-in은 super-step join.
        g.add_edge("coder", "auditor")
        g.add_edge("coder", "generator")
        g.add_edge("auditor", "executor")
        g.add_edge("generator", "executor")
        # Executor는 두 메시지를 super-step에서 함께 받음 (LangGraph가 join)
    else:
        g.add_edge("coder", "auditor")
        g.add_edge("auditor", "generator")
        g.add_edge("generator", "executor")

    g.add_conditional_edges(
        "executor",
        route_after_executor,
        {"architect": "architect", "coder": "coder", "auditor": "auditor",
         "generator": "generator", "evaluator": "evaluator",
         "halt": "halt"},
    )
    g.add_edge("evaluator", END)
    g.add_edge("halt", END)

    # P0: SqliteSaver checkpointer — 노드 단위 상태 지속화
    checkpointer = SqliteSaver.from_conn_string(checkpoint_db) if checkpoint_db else None
    return g.compile(checkpointer=checkpointer)
```

**LangGraph 핵심 개념:**

| 요소 | 의미 |
|---|---|
| `StateGraph(ProblemState)` | "이 그래프는 ProblemState 타입의 dict를 노드 사이로 흘려보낸다"고 선언. |
| `add_node(name, fn)` | 함수를 노드로 등록. `fn(state)` 형태로 호출됨. 반환된 dict는 자동으로 state에 머지. |
| `add_edge(A, B)` | A 노드 다음엔 무조건 B로 간다. (직선 화살표) |
| `add_conditional_edges(node, router_fn, mapping)` | node 다음에 `router_fn(state)`를 호출, 그 반환값을 `mapping`에서 찾아 다음 노드 결정. (분기 화살표) |
| `START` / `END` | 그래프의 입구/출구를 나타내는 특별한 상수. |
| `g.compile(checkpointer=...)` | 그래프를 실행 가능한 객체로 컴파일. checkpointer를 주면 노드 단위 state가 자동 영속화. |
| `runnable.invoke(state, config={"configurable": {"thread_id": run_id}})` | thread_id를 주면 SqliteSaver가 그 id로 상태를 저장/복구. |
| `runnable.get_state(config)` | 마지막 체크포인트 복구 — `--resume` 구현의 핵심. |

**라우팅·복구 의미론 (그래프 진화 포인트):**

1. **Per-node retry budget** — `route_after_executor`는 글로벌 `iteration_count`만 보지 않고 `node_retry_budget[failed]`도 함께 검사. budget 0이면 즉시 halt → 단일 노드가 무한 self-loop를 도는 병리 패턴 차단.
2. **Cost guard** — 모든 LLM 노드(`architect`, `coder`, `auditor`, `generator`, `evaluator`)는 `LLMCallTracker.record(...)`로 비용을 누적. 라우터가 `sum(llm_calls.cost_usd) > max_cost_usd`이면 `cost_exceeded`로 halt.
3. **Halt 분기 라벨** — `_halt(state)`는 어떤 조건으로 도착했는지 검사해 `final_status`를 `max_iterations` / `budget_exhausted` / `cost_exceeded` 중 하나로 set.
4. **Resume** — `main.py --resume <run_id>`: 동일 `thread_id`로 `runnable.invoke(None, config=...)` 호출 → SqliteSaver가 마지막 super-step부터 이어서 실행. LLM 재호출은 `--replay`와 결합 시 `llm_traces/`에서 읽어 비용 0.
5. **Parallel fan-out (옵션)** — `parallel_fanout=True`일 때 LangGraph가 같은 super-step에서 Auditor와 Generator를 동시에 실행. 둘의 반환 dict는 LangGraph 머저가 union (state 키 충돌 없음 — 각자 다른 필드만 set).

**Python 문법 노트:**

- `state.get("final_status")` — dict의 안전한 키 접근. `state["final_status"]`는 키가 없으면 KeyError, `state.get(...)`은 `None` 반환 (또는 기본값을 두 번째 인자로).
- `state.get("iteration_count", 0)` — 키가 없으면 `0` 반환.
- `failed in ("architect", "coder", ...)` — tuple 멤버십 체크.
- `_halt`처럼 `_`로 시작하는 함수 = 모듈 내부용.
- `dict | None` (3.10+) — `Optional[dict]`의 짧은 표기.
- `sum(c.get("cost_usd", 0.0) for c in state.get("llm_calls", []))` — 제너레이터 표현식 + `sum()`. `llm_calls`가 비었으면 0.0.

---

### 3.5 `ipe/nodes/architect.py` — 문제 설계자

```python
SYSTEM_PROMPT = """You are The Architect — ..."""    # 모듈 레벨 상수

USER_TEMPLATE = """target_algorithm: {algorithm}
"""


def run(state: ProblemState) -> ProblemState:
    chat = get_chat(ARCHITECT_MODEL, max_tokens=4096)
    user = USER_TEMPLATE.format(
        algorithm=state["target_algorithm"],
    )
    feedback = state.get("feedback_message")
    if feedback:
        user += FEEDBACK_SUFFIX.format(feedback=feedback)

    resp = chat.invoke([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ])
    data = parse_json_block(resp.content)

    samples = data.get("sample_testcases", [])
    if len(samples) < 3:
        raise ValueError(f"Architect returned too few sample_testcases: {len(samples)}")

    return {
        **state,                                          # 기존 state 전체 풀어 넣기
        "problem_title": data["problem_title"],
        "problem_description": data["problem_description"],
        "constraints": data["constraints"],
        "sample_testcases": samples,
        "feedback_message": None,
        "last_failed_node": None,
    }
```

**핵심 책임:**
- 알고리즘 유형을 받아 **창의적인 새 문제** 생성 (난이도는 사전 지정하지 않음 — Evaluator가 사후 측정)
- 문제 본문 (Markdown), 제약조건(자유 서술 + **`constraints_structured` 객체**), **3-5개의 샘플 테스트케이스** (정답 포함) 생성
- 샘플은 사람이 30초 내에 손으로 풀 수 있을 만큼 작게 (N ≤ 5)
- `has_special_judge` (boolean) 출력 — multiple-valid-output 문제 여부

**`constraints_structured` 출력 강제:**

LLM이 `constraints_structured` 키를 누락하거나 형식 오류면 `ValueError`를 던져 self-loop (`last_failed_node="architect"`). Architect는 다음 호출 시 feedback과 함께 다시 시도.

```python
# architect.py 검증 부분 (예시)
def _validate_constraints_structured(cs: dict, raw: str) -> None:
    if not isinstance(cs, dict):
        raise ValueError("constraints_structured must be an object")
    if "time_limit_ms" not in cs or not isinstance(cs["time_limit_ms"], int):
        raise ValueError("constraints_structured.time_limit_ms (int) required")
    if "memory_limit_mb" not in cs or not isinstance(cs["memory_limit_mb"], int):
        raise ValueError("constraints_structured.memory_limit_mb (int) required")
    if "variables" in cs:
        for v in cs["variables"]:
            assert "name" in v and "min" in v and "max" in v, "variables[] schema"
```

이 검증은 명시적으로 코드에 둠 — Executor가 fallback (5초/512MB)을 쓸 수도 있지만, structured constraints가 없으면 problem-specific timeout/memlimit이 무력화되므로 게이트로 강제.

**프롬프트-only 강제의 한계 (REVIEW W2):**
LLM이 첫 시도에서 `constraints_structured`를 누락하면 feedback과 함께 재호출되지만, **재시도에서도 동일한 형식으로 누락할 가능성**이 있다 (프롬프트 변경만으로는 구조 출력 강제가 불충분). 권장 보강:

1. **Anthropic `tool_use` API 활용** — Architect 호출 시 단일 tool `submit_problem`을 정의하고 `constraints_structured`를 required parameter로 선언. LLM이 tool call로만 응답하도록 강제하면 schema 위반이 거의 0에 수렴.
   ```python
   architect_tool = {
       "name": "submit_problem",
       "input_schema": {
           "type": "object",
           "required": ["problem_title", "problem_description", "constraints",
                        "constraints_structured", "sample_testcases", "has_special_judge"],
           "properties": {
               "constraints_structured": {
                   "type": "object",
                   "required": ["time_limit_ms", "memory_limit_mb"],
                   "properties": { ... },
               },
               ...
           },
       },
   }
   chat = ChatAnthropic(model=ARCHITECT_MODEL).bind_tools([architect_tool])
   ```
2. **JSON Schema validator** — 응답을 `jsonschema.validate(data, schema)`로 검증. 위반 시 schema 오류 메시지를 feedback에 포함하여 재시도.
3. **MVP 우선순위:** 프롬프트-only로 시작 → 누락률이 >5%이면 tool_use로 전환. SPEC §7 메트릭으로 누락률 추적.

**Python 문법 노트:**

| 패턴 | 의미 |
|---|---|
| `"""문자열"""` | 여러 줄 문자열 (triple-quoted). 시스템 프롬프트처럼 긴 텍스트를 그대로 넣을 때 사용. |
| `USER_TEMPLATE.format(algorithm=...)` | 문자열 내 `{algorithm}` 자리에 값 삽입. `f"..."` 와 비슷하지만 템플릿을 미리 정의하고 나중에 `format()`으로 채울 때 사용. |
| `user += "..."` | `user = user + "..."` 의 약어 (Java와 동일). |
| `{**state, "key": value}` | **dict unpacking**. 기존 `state`의 모든 키-값을 풀어서 새 dict에 복사한 뒤, 추가 키를 덮어쓰기. **Java로 비유하자면**: `Map<String,Object> copy = new HashMap<>(state); copy.put("key", value); return copy;` |
| `chat.invoke([{...}, {...}])` | LangChain의 표준 메시지 형식 (system/user 메시지 리스트). |

**프롬프트 → JSON → state 업데이트의 패턴**은 모든 LLM 노드 (Architect, Coder, Auditor, Generator, Evaluator)가 공통적으로 따릅니다.

**피드백 처리:** 이전 사이클이 이 노드에서 실패해 다시 호출되었다면 `state["feedback_message"]`에 실패 사유가 들어있고, 프롬프트 끝에 `## Previous Failure Feedback` 섹션으로 첨부됩니다.

---

### 3.6 `ipe/nodes/coder.py` — 골든 솔루션 작성

Architect가 만든 문제를 받아 **정답 코드**를 작성합니다. Java 또는 Python 중 `state["target_language"]`에 따라 분기.

특이점:
- LLM 출력이 JSON 봉투에 코드를 인코딩하기 어렵다는 점을 고려해, **펜스 코드 블록** 형식으로 출력시킵니다.
- 문제가 본질적으로 풀 수 없을 때만 `IMPOSSIBLE: <reason>` 한 줄을 코드 앞에 붙이도록 강제 (이 경우 Architect로 라우팅).

```python
_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)
_IMPOSSIBLE_RE = re.compile(r"^\s*IMPOSSIBLE\s*:\s*(.+)$", re.MULTILINE)


def _parse_response(text: str) -> tuple[str, str | None]:
    matches = list(_FENCE_RE.finditer(text))
    if not matches:
        raise ValueError(...)
    # 가장 큰 펜스 블록을 선택 (실제 솔루션 vs 짧은 설명 블록 구분)
    fence = max(matches, key=lambda m: len(m.group(1)))
    code = fence.group(1)
    impossible_match = _IMPOSSIBLE_RE.search(text[: fence.start()])
    impossible = impossible_match.group(1).strip() if impossible_match else None
    return code, impossible
```

**Python 문법 노트:**

| 패턴 | 의미 |
|---|---|
| `re.compile(r"...")` | 정규표현식 컴파일. `r"..."` 는 raw string — `\\n` 같은 이스케이프를 그대로 보존 (regex에 필수). |
| `re.DOTALL` | `.` 가 줄바꿈도 매칭하도록 하는 플래그. |
| `(?:...)` | 비캡처 그룹. 그룹화는 하되 결과로 추출 안 함. |
| `(?P<name>...)` (generator.py에서) | **이름붙은 캡처 그룹**. `match.group("name")`로 추출 가능. |
| `_FENCE_RE.finditer(text)` | 모든 매치를 iterator로 반환. `list(...)`로 감싸 즉시 리스트화. |
| `max(matches, key=lambda m: len(m.group(1)))` | `key` 함수로 가장 큰 원소 선택. **lambda**는 한 줄 익명 함수 (Java의 `m -> m.length`와 비슷). |
| `impossible_match.group(1).strip() if impossible_match else None` | **삼항 표현식**. Java의 `cond ? a : b` 와 동일하지만 순서가 `값 if 조건 else 값`. |
| `text[: fence.start()]` | 슬라이싱 시작 인덱스 생략 = 0부터. "펜스 시작 전의 문자열" 의미. |
| `tuple[str, str \| None]` | "두 원소 튜플 (str, str또는None)" 타입 힌트. |

**왜 가장 긴 펜스를 골라야 하나:** 모델이 가끔 설명용 펜스 (`// 시간복잡도 분석` 같은 짧은 주석 블록)를 먼저 출력한 뒤 진짜 코드 펜스를 출력합니다. 첫 번째 펜스를 잡으면 주석만 추출되어 컴파일 에러. 가장 긴 펜스가 진짜 솔루션일 확률이 압도적으로 높음.

---

### 3.7 `ipe/nodes/auditor.py` — 손작업 엣지케이스

```python
MIN_ADVERSARIAL_CASES = 8
MAX_ADVERSARIAL_CASES = 15

# SYSTEM_PROMPT는 8-15개의 작은 (입력 ≤200자) 적대적 케이스 요구
# 카테고리: MIN_SIZE, SINGLE_ELEMENT, UNIFORM, BOUNDARY_LOW/HIGH,
#         SORTED_ASC/DESC, DEGENERATE, NUMERICAL_EDGE, ADVERSARIAL


def run(state: ProblemState) -> ProblemState:
    ...
    text = resp.content
    try:
        data = parse_json_block(text)
        inputs = data.get("adversarial_inputs", [])
    except (ValueError, KeyError):
        # 응답이 절단됐을 가능성 → 완성된 entry만 복구
        inputs = parse_json_array_field(text, "adversarial_inputs")

    if len(inputs) < MIN_ADVERSARIAL_CASES:
        return {                                              # 자기 자신에게 재요청
            **state,
            "adversarial_inputs": inputs,
            "feedback_message": f"Only {len(inputs)} ...",
            "last_failed_node": "auditor",
        }
    return {**state, "adversarial_inputs": inputs, ...}
```

**핵심 책임:** 사람이 머리로 짜내는 **작은 저격용 케이스**만 생성. (큰 random/stress 입력은 Generator가 담당.) **expected_output은 만들지 않음** — 솔루션을 oracle로 삼아 Executor가 채움.

**Python 문법 노트:**

- `try / except`: Java의 `try / catch`. `except (ValueError, KeyError):` 처럼 튜플로 여러 예외 동시 처리.
- `f"Only {len(inputs)} ..."`: f-string으로 변수 삽입.
- 이 노드가 자기 자신을 다시 호출하도록 라우팅하는 패턴 (`last_failed_node="auditor"`)은 LangGraph에서 자기 루프(self-loop)를 만드는 방법.

---

### 3.8 `ipe/nodes/generator.py` — 시드 기반 입력 생성기 작성자

이 노드는 **Codeforces Polygon** 패턴을 따라, LLM에게 **Python 스크립트** 자체를 작성하게 합니다. 그 스크립트는 시드를 인자로 받아 큰 입력을 결정론적으로 출력합니다.

왜 이렇게 했나:
- LLM이 100KB짜리 입력을 직접 출력하면 토큰 비용 폭발.
- Generator 스크립트를 한 번 만들고 **로컬에서 시드 1, 2, 3, 4, 5로 5번 실행**하면 5개의 큰 입력이 무료로 나옴.
- 결정론적 (시드 고정) → 재현 가능.

```python
SYSTEM_PROMPT = """...
Output format — NAME/CATEGORY/DESCRIPTION 헤더 + Python 펜스 블록을 반복:

NAME: gen_random_small
CATEGORY: RANDOM_SMALL
DESCRIPTION: <one short line>
```python
<full script>
```
"""

_BLOCK_RE = re.compile(
    r"NAME:\s*(?P<name>\S+)\s*\n"
    r"CATEGORY:\s*(?P<category>\S+)\s*\n"
    r"DESCRIPTION:\s*(?P<description>[^\n]*)\n"
    r"```(?:python)?\s*\n(?P<code>.*?)```",
    re.DOTALL,
)


def _parse(text: str) -> list[dict]:
    out: list[dict] = []
    for m in _BLOCK_RE.finditer(text):
        out.append({
            "name": m.group("name").strip(),
            "category": m.group("category").strip(),
            "description": m.group("description").strip(),
            "code": m.group("code"),
            "seeds": list(DEFAULT_SEEDS_PER_GENERATOR),  # 새 리스트 복사
        })
    return out
```

**Python 문법 노트:**

- 정규식의 `(?P<name>\S+)` — 이름붙은 캡처 그룹. 매치 후 `m.group("name")` 으로 추출.
- `for m in _BLOCK_RE.finditer(text):` — 매치를 하나씩 순회.
- `list(DEFAULT_SEEDS_PER_GENERATOR)` — 리스트의 **얕은 복사**. 원본을 mutate하지 않으려고. (Java의 `new ArrayList<>(seeds)` 와 비슷.)
- `out.append(...)` — 리스트 끝에 추가 (Java `list.add(...)`).

**Generator 스크립트 형태 (LLM이 작성):**
```python
import sys, random
seed = int(sys.argv[1])
random.seed(seed)
n = random.randint(50, 100)
print(n)
print(' '.join(str(random.randint(1, 1000)) for _ in range(n)))
```

이렇게 만들어진 스크립트는 Executor가 `python gen_random_small.py 1`, `python gen_random_small.py 2`, ... 로 실행해 stdin 텍스트를 만들어냅니다.

---

### 3.9 `ipe/nodes/executor.py` — 결정론적 검증 엔진

LLM 개입 없이 **격리 환경(sandbox)에서 물리적으로** 코드를 컴파일/실행하고 채점합니다. 가장 복잡한 노드.

#### 3.9.0 SandboxedRunner 추상화 (`ipe/sandbox/runner.py`)

executor.py는 `subprocess.run`을 직접 호출하지 않고 `SandboxedRunner` 인터페이스를 사용합니다. 이렇게 추상화하면 격리 tier (Docker / nsjail / RLIMIT-only)를 런타임에 교체 가능.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass(frozen=True)
class RunSpec:
    cmd: list[str]                 # 실행 커맨드 (셸 미경유)
    cwd: str                       # 작업 디렉토리
    stdin: str = ""
    time_limit_ms: int = 5000      # wall + CPU 양쪽
    memory_limit_mb: int = 512
    max_stdout_bytes: int = 5 * 1024 * 1024   # 5MB
    max_stderr_bytes: int = 1 * 1024 * 1024   # 1MB
    max_processes: int = 16
    network: bool = False                       # 항상 False 권장

@dataclass(frozen=True)
class RunResult:
    status: str                    # "OK" | "RTE" | "TLE" | "MLE" | "OLE" | "SANDBOX_ERROR"
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: int
    peak_memory_mb: int | None
    truncated_stdout: bool
    truncated_stderr: bool

class SandboxedRunner(ABC):
    @abstractmethod
    def run(self, spec: RunSpec) -> RunResult: ...

    @abstractmethod
    def isolation_self_test(self) -> dict:
        """sandbox_isolation_pass 메트릭용 — 의도적 위반 시도가 차단되는지 검증."""
```

* **`DockerRunner` (T1)** — `docker run --rm --network=none --read-only --tmpfs /work --memory <N>m --cpus <K> --pids-limit <P> ...`. 재사용 가능한 baseline 이미지 (`python:3.11-slim` + JDK).
* **`NsjailRunner` (T2)** — nsjail config 파일 동적 생성. macOS는 `firejail` 또는 sandbox-exec, Linux는 `nsjail`. `bubblewrap`도 옵션.
* **`RlimitRunner` (T3)** — `subprocess.Popen(preexec_fn=lambda: setrlimit(...))`. 네트워크 차단 불가 (best-effort 경고).

런너 선택은 `--sandbox docker|nsjail|rlimit|auto` CLI 옵션으로. `auto`는 docker 가능성 → nsjail/firejail → rlimit 순서로 fallback.

#### 3.9.1 보조 함수들

```python
def _normalize(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.replace("\r\n", "\n").strip().split("\n"))
```
- 줄 끝 공백 / Windows 개행 / 양 끝 공백 등을 정규화해서 `expected vs actual` 비교가 사소한 차이로 깨지지 않게 함.
- `"\n".join(...)` — 리스트의 모든 원소를 `"\n"`으로 이어붙여 하나의 문자열로. (Java `String.join("\n", list)`.)
- `for line in ...` 안의 표현식 `line.rstrip() for line in ...` 은 **제너레이터 표현식** (lazy 리스트 컴프리헨션).

```python
def _write_source(run_dir: Path, language: str, code: str) -> Path:
    if language == "python":
        path = run_dir / "solution.py"
    elif language == "java":
        path = run_dir / "Solution.java"
    ...
    path.write_text(code, encoding="utf-8")
    return path
```
- `Path` 객체끼리 `/` 연산자로 경로 합치기. (`os.path.join` 대신.) Pythonic 한 방식.
- `path.write_text(code, encoding="utf-8")` — 한 줄에 파일 쓰기.

```python
def _compile(run_dir: Path, language: str) -> tuple[bool, str]:
    if language == "java":
        proc = subprocess.run(
            ["javac", "Solution.java"],
            cwd=run_dir, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            return False, proc.stderr or proc.stdout
        return True, ""
```
- `subprocess.run(["javac", "Solution.java"], ...)` — 다른 프로세스 실행. 첫 인자가 리스트여야 안전 (셸 인젝션 방지).
- `cwd=run_dir` — 작업 디렉토리 지정.
- `capture_output=True, text=True` — stdout/stderr를 캡처하고 문자열로 디코드.
- `proc.stderr or proc.stdout` — Python에서 빈 문자열은 falsy. "stderr 비어있으면 stdout을 써라"는 짧은 idiom.
- 반환 타입 `tuple[bool, str]` — 다중 반환값을 튜플로.

#### 3.9.2 솔루션 실행

```python
def _execute_solution(run_dir, language, stdin_text, timeout) -> dict:
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            _run_cmd(language),
            cwd=run_dir,
            input=stdin_text,           # stdin으로 텍스트 주입
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {"status": "TLE", ...}
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return {
        "status": "OK" if proc.returncode == 0 else "RTE",
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        ...
    }
```

상태값 코드:
- `OK` — 정상 종료 (returncode 0)
- `RTE` — Runtime Error (returncode 0이 아님)
- `TLE` — Time Limit Exceeded (timeout 초과)

#### 3.9.3 Generator 실행

```python
def _run_generator(gen_dir, gen_name, seed) -> tuple[bool, str, str]:
    script = gen_dir / f"{gen_name}.py"
    proc = subprocess.run(
        [sys.executable, script.name, str(seed)],   # python <script>.py <seed>
        cwd=gen_dir, capture_output=True, text=True,
        timeout=GENERATOR_TIMEOUT_SECS,
    )
    if proc.returncode != 0:
        return False, "", f"generator rc={proc.returncode}: {proc.stderr[:300]}"
    if len(proc.stdout) > MAX_GENERATED_INPUT_BYTES:
        return False, "", f"generator output exceeds {MAX_GENERATED_INPUT_BYTES} bytes"
    return True, proc.stdout, ""
```
- `sys.executable` — 현재 실행 중인 Python 인터프리터 경로. venv를 쓸 때 같은 venv의 python을 쓰는 게 안전.
- 5MB 출력 상한 — 무한 출력으로 디스크/메모리 폭발 방지.

#### 3.9.4 병렬 case 실행 (P1)

Phase B/C는 case 단위 / (script, seed) 단위로 독립적이므로 `ThreadPoolExecutor`로 병렬화. subprocess는 GIL 영향 없으므로 thread만으로도 충분히 fan-out 가능.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _run_phase_b(runner, run_dir, language, adversarial, time_limit_ms, workers=4):
    futures = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for idx, tc in enumerate(adversarial):
            fut = pool.submit(_execute_solution, runner, run_dir, language,
                              tc["input"], time_limit_ms)
            futures[fut] = (idx, tc)
        results = []
        for fut in as_completed(futures):
            idx, tc = futures[fut]
            results.append((idx, tc, fut.result()))
    return sorted(results, key=lambda x: x[0])    # 순서 보존
```

* 기본 worker = 4 (`--exec-workers`로 조정).
* 컴파일은 1회 직렬, 실행만 병렬.
* sandbox tier가 Docker일 경우 컨테이너 재사용을 위해 `docker run` 대신 미리 시작된 컨테이너에 `docker exec`하는 패턴 권장 (cold start ~500ms 절감).

#### 3.9.5 메인 `run(state)` — 3-Phase 검증

```python
def run(state: ProblemState) -> ProblemState:
    language = state.get("target_language", "python")
    samples = state.get("sample_testcases", [])
    adversarial = state.get("adversarial_inputs", [])
    generators = state.get("generators", [])

    # 1) workdir 생성, 솔루션 작성, 컴파일
    WORKDIR_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = WORKDIR_ROOT / f"run_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir()
    gen_dir = run_dir / "generators"
    gen_dir.mkdir()

    next_iter = state.get("iteration_count", 0) + 1

    _write_source(run_dir, language, code)
    ok, compile_err = _compile(run_dir, language)
    if not ok:
        return {..., "last_failed_node": "coder", "feedback_message": compile_err}

    # 2) 노드별 산출물 누락 체크 (early return)
    if not samples:    return {..., "last_failed_node": "architect"}
    if not adversarial: return {..., "last_failed_node": "auditor"}
    if not generators:  return {..., "last_failed_node": "generator"}

    # generator 스크립트들을 디스크에 저장
    for g in generators:
        (gen_dir / f"{g['name']}.py").write_text(g["code"], encoding="utf-8")

    results: list[dict] = []
    final_testcases: list[dict] = []

    # ─── Phase A: Sample correctness ───
    # Architect가 준 expected_output과 솔루션 출력 비교 (정확성 검증)
    for idx, tc in enumerate(samples):
        out = _execute_solution(run_dir, language, ...)
        passed = out["status"] == "OK" and actual == expected_norm
        results.append({...})
        final_testcases.append({"kind": "sample", ...})
        if not passed:
            sample_failures.append(...)

    if sample_failures:
        # 휴리스틱 라우팅:
        #   다수 통과 + 소수 실패 + 크래시 없음 → Architect (sample 오답일 가능성)
        #   다수 실패 또는 크래시 → Coder (솔루션 버그)
        ...

    # ─── Phase B: Adversarial small inputs ───
    # 솔루션이 RTE/TLE 안 나면 합격, 출력값은 oracle로 testcase에 추가
    for idx, tc in enumerate(adversarial):
        out = _execute_solution(...)
        passed = out["status"] == "OK"
        if passed:
            final_testcases.append({"kind": "adversarial",
                                    "expected_output": actual, ...})
        else:
            adv_failures.append(...)

    if adv_failures:
        return {..., "last_failed_node": "coder"}

    # ─── Phase C: Generator-based stress ───
    # 각 generator를 시드별로 실행 → 솔루션 통과시 oracle로 testcase 추가
    for g in generators:
        for seed in g.get("seeds", []):
            ok, stdin_text, gen_err = _run_generator(gen_dir, g["name"], seed)
            if not ok:
                # generator 스크립트가 깨짐 → Generator 노드로 라우팅
                continue
            out = _execute_solution(run_dir, language, stdin_text, ...)
            if out["status"] == "OK":
                final_testcases.append({"kind": "generated",
                                        "expected_output": actual, ...})
            else:
                gen_failures.append(...)

    if gen_failures:
        # gen 스크립트 자체가 깨졌으면 Generator로, 솔루션 RTE/TLE면 Coder로
        target = "generator" if any_gen_script_failed and not any_sol_failed else "coder"
        return {..., "last_failed_node": target}

    # ─── Phase C 추가 게이트: 정해 성능 검증 (P2) ───
    max_stress_elapsed = max(r["elapsed_ms"] for r in stress_results)
    if max_stress_elapsed > time_limit_ms * 0.5:
        return {..., "last_failed_node": "coder",
                "feedback_message": f"solution too slow: {max_stress_elapsed}ms > {time_limit_ms*0.5:.0f}ms (50% of limit)"}

    # 모두 통과 → success
    return {..., "final_status": "success"}
```

**핵심 설계 결정:**
1. **Sample correctness** = Architect의 expected_output을 oracle로 사용 (이게 유일한 외부 진실원). `has_special_judge=true`일 경우 stdout 비교 대신 `special_judge_code` 실행.
2. **Adversarial / Generated**의 expected_output = 골든 솔루션 출력 자체. 즉 **회귀 테스트 베이스라인**. 솔루션이 다음에 같은 동작을 하는지 확인하는 용도.
3. **Sample WA의 휴리스틱 라우팅 (3-way, REVIEW W3 보강):**
    - **다수 통과 + 소수 실패 + 크래시 없음**: 5개 중 4개 통과 + 1개 실패 = 솔루션은 정상이고 Architect가 손계산 틀렸을 확률이 높음 → **Architect**.
    - **전체 실패 + 컴파일 OK + 솔루션이 모든 sample에 대해 일관된 출력 생성** (예: 5개 모두 다른 답을 내지만 RTE/TLE 없음): 솔루션은 어떤 일관된 풀이를 따르고 있고 sample 전체가 잘못됐을 가능성 → **Architect** (신규 분기). 휴리스틱: `n_pass == 0 and all(r["status"] == "OK" for r in sample_results) and len({r["actual"] for r in sample_results}) == len(sample_results)` (모든 출력이 서로 다름 = 입력별 결정론적 결과).
    - **다수 실패 + 출력 패턴 불일관 또는 크래시 동반**: 솔루션 자체가 잘못됨 → **Coder**.
    - 위 분기는 `iteration_history`에 `error_signature="phase_a_all_fail_consistent"` 등으로 기록되어 다음 사이클에서 동일 분기 반복 시 다른 노드(예: 두 번째 시도는 Coder)로 전환.
4. **Adversarial 입력 syntactic validator** — Phase B 실행 전, 각 input이 `constraints_structured.variables`의 범위와 형식을 준수하는지 파싱 검사. 위반 시 → Auditor로 (input 자체가 잘못됨, 솔루션 책임 아님). 이 게이트가 없으면 잘못된 input 때문에 Coder로 잘못 라우팅되어 oscillation 유발.
5. **정해 성능 게이트 (Phase C 후)** — max-stress 케이스에서 정해 wall_time이 `time_limit_ms × 0.5`를 넘으면 `oracle slow` 시그널과 함께 Coder로. 이 게이트가 없으면 "느린 정답"을 oracle로 베이스라인 박제하게 됨 → 향후 더 빠른 정답이 등장해도 출력 차이가 없으면 못 잡음.

**iteration_history 기록:** 모든 라우팅 시 `state["iteration_history"]`에 `{iter_index, node, action, error_signature, feedback}` 레코드 추가. `error_signature`는 짧은 해시 (예: `"wa_phase_a_idx_2"`, `"tle_phase_c_seed_3"`). Coder/Auditor 등이 다음 호출 시 이 history를 프롬프트에 동봉받아 **이미 시도한 fix를 반복하지 않음**.

**Oscillation 방지 — 명시적 지시 (REVIEW W4):**
프롬프트에 history만 첨부하면 LLM이 무시하고 같은 fix를 반복할 위험이 있다. 따라서 노드별 user 프롬프트 끝에 다음 패턴을 명시적으로 추가:

```python
def _build_history_section(history: list[dict], current_node: str) -> str:
    own = [h for h in history if h["node"] == current_node]
    if not own:
        return ""
    lines = [f"## Previous {current_node} Attempts (이전 시도 — 반드시 다른 접근법을 사용하라)"]
    for h in own:
        lines.append(f"- iter {h['iter_index']}: action={h['action']}, "
                     f"error_signature={h['error_signature']}")
        lines.append(f"  feedback: {h['feedback'][:200]}")
    sigs = [h["error_signature"] for h in own]
    # 동일 error_signature가 2회 이상 발생했으면 강한 경고
    repeats = [s for s in set(sigs) if sigs.count(s) >= 2]
    if repeats:
        lines.append(f"\n⚠️ 다음 error_signature가 {sigs.count(repeats[0])}회 반복 발생: "
                     f"{repeats}. 이전과 동일한 접근법을 시도하지 말고 근본적으로 다른 전략을 사용하라.")
    return "\n".join(lines)
```

* 라우팅 시 같은 `(node, error_signature)` 쌍이 2회 이상 발생하면 자동으로 강한 경고 문구 삽입 → LLM이 동일 fix를 반복하지 않도록 유도.
* 메트릭 `iteration_oscillation_rate` (SPEC §7.3)는 `error_signature` 중복 빈도로 계산. 임계값 >10%이면 프롬프트 보강 필요 신호.

**Python 문법 노트:**

| 패턴 | 의미 |
|---|---|
| `for idx, tc in enumerate(samples):` | 인덱스와 값을 동시에 순회. (Java의 `for (int i=0; i<list.size(); i++)` 보다 깔끔.) |
| `n_pass * 2 > len(sample_results)` | "n_pass / total > 0.5" 를 정수 산술로. |
| `any(r["status"] in ("RTE", "TLE") for r in sample_results)` | 제너레이터 표현식 + `any()`. "한 개라도 조건 만족하면 True". |
| `sum(1 for r in sample_results if r["pass"])` | 통과 개수 세기. |
| `[r for r in results if r["phase"] == "sample"]` | **리스트 컴프리헨션** — 필터링한 새 리스트. (Java의 `stream().filter().collect()`.) |
| `uuid.uuid4().hex[:8]` | 무작위 UUID의 처음 8글자만 추출 (디렉토리 이름용). |

---

### 3.10 `ipe/nodes/evaluator.py` — 난이도 사후 측정

Executor가 `final_status="success"`를 반환한 후에만 호출됩니다. 검증을 통과한 완성된 문제의 난이도를 종합적으로 평가합니다.

**핵심 책임:**
- 문제 지문 + 제약조건 (raw + structured) + 정해 코드 + 실행 결과를 종합적으로 분석
- 단순히 알고리즘 이름으로 난이도를 때려맞추는 것이 아닌, 제약조건의 타이트함·구현 복잡도·엣지케이스까지 고려
- `difficulty_reasoning`에 판정 근거를 상세히 기술하여 Human Review 가능하게
- **Calibration Anchor Set 동봉** — 백준 표준 난이도별 reference 샘플을 프롬프트에 포함하여 anchor 대비 상대적 위치 판단 (run-to-run 분산 축소).

```python
# evaluator.py
import json
from ipe.calibration import load_anchors
from ipe.llm import get_chat, parse_json_block

EVALUATOR_MODEL = "claude-opus-4-7"
ANCHORS = load_anchors()  # [{id, label, summary, factors}, ...]

SYSTEM_PROMPT = """You are The Evaluator — a competitive programming difficulty assessor.
You analyze a fully verified problem and assign a difficulty rating.

Evaluate based on these factors:
- algorithm_complexity: theoretical difficulty of the core algorithm
- implementation_difficulty: how hard it is to code correctly
- edge_case_density: how many traps and corner cases exist
- constraint_tightness: whether constraints force optimal solutions
- conceptual_leap: how non-obvious the problem-to-algorithm mapping is

Use the provided Calibration Anchors as a relative reference. State which
anchor the target problem is closest to in your reasoning.

Return JSON:
{
  "difficulty_label": "Gold 3",          // 백준 기준 (Bronze5 ~ Ruby1)
  "difficulty_reasoning": "...",         // 판정 근거 상세 (어떤 anchor와 가장 가까운지 명시)
  "difficulty_factors": {
    "algorithm_complexity": "...",
    "implementation_difficulty": "...",
    "edge_case_density": "...",
    "constraint_tightness": "...",
    "conceptual_leap": "..."
  }
}
"""


def _build_anchor_block(anchors: list[dict]) -> str:
    lines = ["## Calibration Anchors (백준 표준 난이도별 reference)"]
    for a in anchors:
        lines.append(f"- [{a['label']}] ({a['id']}): {a['summary']}")
        lines.append(f"  factors: {a['factors']}")
    return "\n".join(lines)


def run(state: ProblemState) -> ProblemState:
    chat = get_chat(EVALUATOR_MODEL, max_tokens=2048)
    anchor_block = _build_anchor_block(ANCHORS)
    user = f"""## Problem
{state['problem_description']}

## Constraints (raw)
{state['constraints']}

## Constraints (structured)
{json.dumps(state.get('constraints_structured', {}), ensure_ascii=False, indent=2)}

## Solution Code
```
{state['solution_code']}
```

## Execution Summary
Total testcases: {len(state.get('testcases', []))}
Max stress wall_time: {max((r['elapsed_ms'] for r in state.get('execution_results', [])), default=0)}ms

{anchor_block}

지시: 위 anchor들과 비교하여 이 문제의 난이도를 판정하고, 어떤 anchor와 가장 가까운지 reasoning에 명시.
"""
    resp = chat.invoke([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ])
    data = parse_json_block(resp.content)

    return {
        **state,
        "difficulty_label": data["difficulty_label"],
        "difficulty_reasoning": data["difficulty_reasoning"],
        "difficulty_factors": data.get("difficulty_factors", {}),
        "difficulty_calibration_anchors": [a["id"] for a in ANCHORS],
    }
```

`anchors.json` 예시 스키마:
```json
[
  {"id": "bj_2557_bronze5", "label": "Bronze 5",
   "summary": "Hello World 출력. 알고리즘 없음.",
   "factors": {"algorithm_complexity": "none", "implementation_difficulty": "trivial"}},
  {"id": "bj_1753_gold4", "label": "Gold 4",
   "summary": "최단경로 (Dijkstra). V≤20000, E≤300000.",
   "factors": {"algorithm_complexity": "Dijkstra+PQ", "constraint_tightness": "O((V+E)logV) 강제"}}
]
```

**피드백 루프 없음:** Evaluator는 검증 통과 후 한 번만 실행되며, 실패 시 재시도하지 않습니다. `evaluator → END` 직선 엣지. Difficulty ensemble (다수 평가자 투표)은 P2 — Future.

---

### 3.11 `ipe/io.py` — 산출물 영속화

LangGraph 사이클이 끝난 뒤 최종 state를 디스크에 저장합니다. **Codeforces Polygon 스타일**:

```
outputs/<run_id>/                  # 1차 디렉토리 (uuid)
├─ problem.json        # DB-insertable (작은 testcase는 inline, 큰 건 manifest 참조)
├─ problem.md          # 사람이 읽는 형태
├─ solution.py 또는 Solution.java
├─ generators/
│  ├─ gen_random_small.py
│  ├─ gen_random_medium.py
│  ├─ gen_max_stress.py
│  └─ ...
├─ tests/
│  ├─ 01.in / 01.out
│  ├─ 02.in / 02.out
│  ├─ ...
│  ├─ NN.in / NN.out
│  └─ manifest.json    # 각 케이스의 메타 (kind, category, generator, seed, exec_time)
├─ llm_traces/         # §3.12 참조
└─ checkpoint.db       # SqliteSaver

outputs/by-name/<timestamp>_<algo>  → ../<run_id>   # 사람이 찾기 좋은 별칭 심볼릭 링크
```

`<run_id>`는 sandbox/checkpoint/llm_traces 모두에서 사용되는 단일 식별자. 사람이 읽기 위한 `<timestamp>_<algo>` 폴더는 `outputs/by-name/`에 별칭 symlink로만 생성하여 본 경로를 분리.

```python
def save_result(state: ProblemState, outputs_root: Path) -> Path:
    run_id = state["run_id"]
    folder = outputs_root / run_id
    folder.mkdir(parents=True, exist_ok=True)

    # 사람이 찾기 위한 별칭 symlink (선택적, 충돌 시 skip)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    alias_dir = outputs_root / "by-name"
    alias_dir.mkdir(exist_ok=True)
    alias = alias_dir / f"{ts}_{_slug(state.get('target_algorithm', 'algo'))}"
    if not alias.exists():
        alias.symlink_to(Path("..") / run_id)

    # 솔루션 파일
    sol_name = "Solution.java" if language == "java" else "solution.py"
    (folder / sol_name).write_text(state.get("solution_code", ""), encoding="utf-8")

    # generators/<name>.py
    for g in generators:
        (gen_dir / f"{g['name']}.py").write_text(g.get("code", ""), encoding="utf-8")

    # tests/NN.in, NN.out + manifest
    width = max(2, len(str(len(testcases))))    # 케이스 수에 맞춰 zero-pad 폭 결정
    for i, tc in enumerate(testcases, start=1):
        stem = str(i).zfill(width)               # "1" → "01" 또는 "001"
        in_path = tests_dir / f"{stem}.in"
        out_path = tests_dir / f"{stem}.out"
        ...

    # problem.json
    inline_testcases = [tc for tc in testcases if tc.get("kind") in ("sample", "adversarial")]
    problem_record = {
        "meta": {...},
        "problem": {...},
        "solution": {...},
        "generators": [...],
        "testcases_inline": inline_testcases,    # 작은 것만 inline
        "testcase_manifest": manifest_entries,    # 모든 케이스 → 파일 포인터
        "execution_results": ...,
    }
    (folder / "problem.json").write_text(json.dumps(problem_record, ensure_ascii=False, indent=2))
```

**Python 문법 노트:**

- `str(i).zfill(width)` — 숫자를 문자열로 바꾸고 width만큼 0으로 좌측 패딩. `1 → "01"`.
- `enumerate(testcases, start=1)` — 인덱스를 1부터 시작.
- `re.sub(r"[^a-zA-Z0-9_-]+", "-", s)` — 정규식 치환 ("알파벳/숫자/_/- 가 아닌 문자" → "-"). 안전한 디렉토리 이름 만들기 (slugify).
- `json.dumps(obj, ensure_ascii=False, indent=2)` — JSON 직렬화. `ensure_ascii=False` 가 있어야 한글이 `\uXXXX` 로 이스케이프 안 됨.

**왜 inline + manifest 이중 저장:**
- DB 인서트용으로는 한 row에 모든 testcase가 들어있는 게 편하지만, generated 케이스는 한 개에 수십 MB까지 갈 수 있어 DB row가 비대해짐.
- 그래서 **작은 sample/adversarial만 problem.json에 inline**, 큰 generated는 `tests/NN.in/.out` 파일로 분리하고 manifest로 참조.

---

### 3.12 `ipe/observability.py` — LLM 호출 회계, 메트릭, 로깅

P1 — 모든 LLM 호출에 자동으로 토큰·비용·trace를 부착하는 thin wrapper. 노드별로 `LLMCallTracker`를 통해 호출하면, `state["llm_calls"]`에 자동으로 누적되고 `outputs/<run_id>/llm_traces/<seq>_<node>.json`에 raw가 저장됨.

```python
import json, time, uuid
from pathlib import Path
from typing import Any
from langchain_anthropic import ChatAnthropic

# Claude 모델별 토큰 가격 (USD per 1M tokens) — 갱신 필요시 한 곳에서만
PRICING = {
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input":  3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
}

def _cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    p = PRICING.get(model, {"input": 0, "output": 0})
    return (in_tok * p["input"] + out_tok * p["output"]) / 1_000_000


class LLMCallTracker:
    def __init__(self, run_id: str, traces_dir: Path):
        self.run_id = run_id
        self.traces_dir = traces_dir
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        self.seq = 0

    def invoke(self, chat: ChatAnthropic, messages: list, *, node: str,
               state_calls: list) -> Any:
        self.seq += 1
        seq = self.seq
        ts = time.time()
        resp = chat.invoke(messages)
        usage = getattr(resp, "usage_metadata", {}) or {}
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        model = chat.model
        cost = _cost_usd(model, in_tok, out_tok)

        trace_path = self.traces_dir / f"{seq:04d}_{node}.json"
        trace_path.write_text(json.dumps({
            "seq": seq, "node": node, "model": model,
            "messages": messages, "response": resp.content,
            "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": cost, "timestamp": ts,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        state_calls.append({
            "seq": seq, "node": node, "model": model,
            "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": cost, "timestamp": ts,
            "trace_path": str(trace_path.relative_to(self.traces_dir.parent.parent)),
        })
        return resp


class ReplayTracker(LLMCallTracker):
    """--replay 모드: 새 LLM 호출 대신 기존 trace를 읽어 재사용. 비용 0."""
    def invoke(self, chat, messages, *, node, state_calls):
        self.seq += 1
        # messages 해시로 매칭하거나 seq 순서 기반 매칭
        ...
```

**메트릭 표준 (구조적 로깅 키):**

| 메트릭 | 시점 | 라벨 |
|---|---|---|
| `ipe.node.latency_ms` | 노드 종료 | `node`, `iter_index` |
| `ipe.llm.tokens.input` | LLM 호출 후 | `node`, `model` |
| `ipe.llm.tokens.output` | LLM 호출 후 | `node`, `model` |
| `ipe.llm.cost_usd` | LLM 호출 후 | `node`, `model` |
| `ipe.executor.phase_latency_ms` | Phase A/B/C 종료 | `phase` |
| `ipe.executor.case_status` | 케이스 종료 | `phase`, `status` (OK/RTE/TLE/MLE/OLE) |
| `ipe.problem.iterations` | 사이클 종료 | `target_algorithm`, `final_status` |
| `ipe.problem.cost_usd` | 사이클 종료 | `target_algorithm`, `final_status` |

* MVP는 `logging` + JSON formatter로 stdout export.
* (옵션) `IPE_LANGSMITH=1` → LangSmith trace export.
* (옵션) `IPE_OTEL_ENDPOINT=...` → OpenTelemetry collector로 push.

---

## 4. Python 문법 / LangGraph 패턴 / 흔한 실수

> **이전 위치:** ARCH §4 (Python 핵심 문법), §5 (LangGraph 핵심 패턴), §7 (흔한 실수)에 있던 교육 콘텐츠는 별도 문서로 분리되었다.
>
> ➡️ **참고:** [`PYTHON_GUIDE.md`](PYTHON_GUIDE.md)
>
> - [§1 Python 핵심 문법 정리](PYTHON_GUIDE.md#1-python-핵심-문법-정리-이-프로젝트에서-자주-등장)
> - [§2 LangGraph 핵심 패턴](PYTHON_GUIDE.md#2-langgraph-핵심-패턴)
> - [§3 흔한 실수와 디버깅 포인트](PYTHON_GUIDE.md#3-흔한-실수와-디버깅-포인트)
> - [§4 모듈별 자주 등장하는 Python 관용구](PYTHON_GUIDE.md#4-모듈별-자주-등장하는-python-관용구)
> - [§5 TypedDict 사용 노트](PYTHON_GUIDE.md#5-typeddict-사용-노트)
> - [§6 타입 힌트 cheat sheet](PYTHON_GUIDE.md#6-타입-힌트-cheat-sheet)
>
> 분리 이유: 본 문서는 IPE 시스템의 **설계**를 다루고, 교육 콘텐츠는 PYTHON_GUIDE.md로 옮겨 CLI 에이전트의 컨텍스트 효율을 보전한다 (REVIEW_REPORT M1).

---

## 6. 산출물 구조 (DB 인서트 관점)

> **스키마 SSOT:** `problem.json`의 전체 필드 정의는 [`PROJECT_SPEC.md §6`](PROJECT_SPEC.md#6-산출물-구조-polygon-style)에 단일 정의됨. 이 섹션은 그 스키마를 **DB 인서트 관점**에서 어떻게 매핑할지만 다룬다. 필드를 추가/변경하려면 SPEC을 먼저 수정한다.

### 6.1 디스크 레이아웃 → DB 테이블 매핑

| DB 테이블 | 행 수 | 출처 (problem.json 경로) | 비고 |
|---|---|---|---|
| `problems` | 1 | `meta` + `problem` + `difficulty` + `constraints_structured` | 한 문제당 한 행. `run_id` PK. |
| `solutions` | 1 | `solution` | language별 분리 시 N행. |
| `generators` | N | `generators[]` | `(run_id, name)` 복합 PK. |
| `testcases` | M | `testcase_manifest[]` | 큰 입출력은 BLOB 또는 외부 스토리지 경로(`tests/NN.in`, `tests/NN.out`) 참조. |
| `execution_results` | K | `execution_results[]` | phase별 인덱스 (sample/adversarial/generated). |
| `iteration_history` | I | `iteration_history[]` | (run_id, iter_index) 복합 PK. 디버깅·재학습용. |
| `llm_calls` | L | `llm_calls[]` | (run_id, seq) 복합 PK. 비용 분석. |

### 6.2 inline vs manifest 이중 저장

- **inline (`testcases_inline`)**: sample + adversarial만 — 작아서 DB row에 직접 적재 가능.
- **manifest (`testcase_manifest`)**: **모든** 케이스의 메타 + 파일 포인터 — 큰 generated 케이스는 파일/오브젝트 스토리지로.
- DB는 manifest를 row로, 큰 입출력은 file_path 또는 BLOB로 저장.

### 6.3 인덱싱 권장

| 인덱스 | 컬럼 | 용도 |
|---|---|---|
| `problems_algo_idx` | `meta.target_algorithm` | 알고리즘별 검색 |
| `problems_difficulty_idx` | `difficulty.label` | 난이도별 검색 |
| `testcases_runid_idx` | `run_id` | 한 문제의 모든 케이스 조회 |
| `llm_calls_cost_idx` | `cost_usd DESC` | 고비용 호출 분석 |

---

## 7. 흔한 실수와 디버깅 포인트 (이전됨)

➡️ [`PYTHON_GUIDE.md §3`](PYTHON_GUIDE.md#3-흔한-실수와-디버깅-포인트) 참조. (REVIEW_REPORT M1로 분리)

---

## 8. 확장 포인트

향후 작업 시 손볼 위치 (P-priority는 PROJECT_SPEC.md §8 참조):

1. **Sub-agent 분해 (P2)** — `ipe/nodes/architect.py` 의 `SYSTEM_PROMPT` 상수를 `Story_Agent` / `Constraint_Agent` 프롬프트로 분리. `architect.run()` 을 두 단계 호출로 바꾸기.
2. **새 언어 지원 (C++, Rust, Go) (P2)** — `executor.py` 의 `_write_source` / `_compile` / `_run_cmd` 의 if/elif 체인을 dict 기반 핸들러로 리팩토링:
   ```python
   LANGUAGE_HANDLERS = {
       "python": {"write": ..., "compile": ..., "run": ...},
       "java":   {"write": ..., "compile": ..., "run": ...},
       "cpp":    {"write": ..., "compile": ..., "run": ...},
   }
   ```
   동시에 sandbox 이미지에 해당 toolchain 추가 필요.
3. **Special judge (P2)** — `has_special_judge=true` 문제에 대해 LLM이 `checker.py`를 생성하는 옵셔널 노드(`special_judge.py`) 추가. Phase A의 비교 로직이 stdout exact match 대신 checker 호출로 대체.
4. **Brute-force cross-check (P2)** — Coder가 골든 + 브루트포스 두 개를 작성하게 하고, 작은 케이스에서 둘의 출력이 일치하는지 교차 검증. 두 솔루션의 출력 불일치 → Coder로 (golden 의심).
5. **난이도 앙상블 (P2)** — Evaluator를 다수 에이전트로 분리하여 독립적으로 평가 후 투표/평균으로 최종 난이도 결정. 평가자 간 편차(분산)가 임계치 초과 시 `human_review_required` 플래그 set.
6. **중복/유사문제 detection (P2)** — `outputs/index.jsonl`에 `(algo, title, description_embedding)`을 누적. 새 문제 저장 직전 코사인 유사도 ≥0.9이면 Architect 재호출 (`feedback="too similar to <id>"`).
7. **Cost-aware model routing** — `coder` 노드가 첫 시도는 Sonnet, 실패 시 Opus로 escalate. `auditor`/`generator`도 단순 case는 Haiku로 cost-down.
8. **Brute-force generator** — Generator가 솔루션 출력을 계산하기 위한 브루트포스 코드를 함께 생성하면 `expected_output`을 정해와 독립적으로 검증 가능 (golden bias 차단).
9. **Persistent JVM** — Java 솔루션의 JVM cold start ~1-2s가 Phase B/C 누적 비용. GraalVM native-image 또는 nailgun을 sandbox 안에서 활용.
10. **Multi-language oracle cross-check** — 같은 문제를 Python/Java 둘 다 작성하게 하여 두 출력이 일치하는지 비교 (구현 일치성).

---

## 9. 운영 가드레일 (Sandbox / Cost / Observability / Replay)

P0/P1 항목들이 어떻게 함께 작동하는지 요약. 각 가드레일은 **독립적으로** halt를 트리거할 수 있고, 가장 먼저 도달하는 것이 우선.

### 9.1 Sandbox 정책 결정 흐름

```
main.py --sandbox <tier>
        │
        ▼
   ┌──────────────┐
   │ tier="auto"? │── yes ─► docker 가능? ── yes ─► T1 (DockerRunner)
   └──────┬───────┘                          no
          │ no                                ▼
          │                            nsjail/firejail 가능?
          │                                   │ yes
          │                                   ▼
          │                              T2 (NsjailRunner)
          │                                   │ no
          │                                   ▼
          │                              T3 (RlimitRunner) + 경고 로그
          ▼
   명시적 tier (T1/T2/T3) 직행
```

* MVP 기본 = `auto` (T2 우선). CI/배포는 `--sandbox docker` 권장.
* `isolation_self_test()` 결과를 `meta.sandbox_isolation_pass`에 기록. 실패 시 `--strict-sandbox` 모드는 즉시 abort.

### 9.2 비용 가드 흐름

```
모든 LLM 노드:
  resp = tracker.invoke(chat, messages, node="...", state_calls=state["llm_calls"])
       │
       ▼
  state["llm_calls"]에 cost_usd 누적
       │
       ▼
route_after_executor:
  if sum(llm_calls.cost_usd) > max_cost_usd:
      → halt (final_status="cost_exceeded")
```

* 사이클 종료 후 `meta.llm_call_summary.total_cost_usd` 기록.
* (옵션) `--cost-warn-usd 2.0` — 경고 임계치. 초과 시 로그만, halt는 안 함.

### 9.3 Resume / Replay 매트릭스

| 모드 | 옵션 | 동작 | LLM 호출 비용 | 사용 시점 |
|---|---|---|---|---|
| **Fresh** | (기본) | 새 run_id 발급, 처음부터 실행 | 정상 | 새 문제 생성 |
| **Resume** | `--resume <run_id>` | 동일 thread_id로 SqliteSaver에서 복구. 마지막 super-step 이후 재실행. | 재실행한 노드만 정상 비용 | crash/network 단절 후 재개 |
| **Replay** | `--replay <run_id>` | LLM 호출을 `llm_traces/`에서 cache hit. Executor만 새로 실행. | $0 | 디버깅, regression 검증 |
| **Resume+Replay** | `--resume <run_id> --replay` | 둘 다 적용. checkpoint 복구 + LLM trace 재생. | $0 (LLM은 trace, executor는 다시 격리실행) | 가장 빠른 재현 |

### 9.4 메트릭 → 경고 매핑 (운영)

| 메트릭 | 경고 임계 | 의미 / 조치 |
|---|---|---|
| `iteration_oscillation_rate` | >10% | iteration_history feedback이 부족 → 프롬프트 보강 |
| `phase_failure_distribution.A > 50%` | — | Architect의 sample 손계산 빈도 높음 → Architect 모델/프롬프트 강화 |
| `phase_failure_distribution.C > 40%` | — | Generator stress가 솔루션 깨뜨림 잦음 → Coder 프롬프트에 stress 의식적 처리 강조 |
| `cost_per_problem.p95 > 0.8 × max_cost_usd` | — | 가드 임계 임박 — 비용 가드/모델 escalation 정책 검토 |
| `sandbox_isolation_pass=false` | — | **즉시 alert**. T3 fallback이 부적절한 환경에서 작동 중일 수 있음 |
| `wallclock vs cpu_time 차이 > 30%` | — | 호스트 noise → CI 환경 격리 점검 |

### 9.5 가드레일 우선순위

가드레일이 동시에 트리거 가능한 경우, 적용 순서:

1. **`sandbox_isolation_pass=false` (with `--strict-sandbox`)** → 즉시 abort
2. **`cost_exceeded`** (가드가 가장 비싸므로 먼저 차단)
3. **`budget_exhausted`** (per-node)
4. **`max_iterations`** (글로벌 안전망)
5. **`success`** (정상 종료)

`final_status`는 위 순서로 set되며, 한 번 set되면 후속 노드에서 덮어쓰지 않음 (`final_status: Optional[str]`이지만 set-once semantics는 코드에서 강제).
