# IPE Python 문법·LangGraph 가이드

> **목적**: Python에 익숙하지 않은 독자(예: Java 위주 백엔드 개발자)를 위한 IPE 코드 이해용 참고 문서. **아키텍처 설계는 [`ARCHITECTURE.md`](ARCHITECTURE.md)**, 본 문서는 **그 안에 등장하는 Python/LangGraph 관용구 해설**만 담는다.
>
> **분리 이유 (REVIEW_REPORT M1)**: 교육 콘텐츠가 아키텍처 문서에 혼재하면 CLI 에이전트의 컨텍스트 효율을 떨어뜨린다. 설계 문서(ARCHITECTURE.md)에서는 본 가이드를 링크 참조로만 다루고, 실제 학습은 여기서 한다.

---

## 1. Python 핵심 문법 정리 (이 프로젝트에서 자주 등장)

| 문법 | 예시 | 의미 |
|---|---|---|
| `def f(x: int) -> str:` | 함수 시그니처 | 타입 힌트. 런타임 강제 X, IDE/도구만 활용. |
| `from x import y` | 모듈 import | Java `import x.Y;` |
| `x = {"a": 1, "b": 2}` | dict 리터럴 | Java `Map.of("a", 1, "b", 2)`. |
| `x = [1, 2, 3]` | list 리터럴 | Java `List.of(1, 2, 3)`. |
| `x = {1, 2, 3}` | set 리터럴 | Java `Set.of(...)`. |
| `x = (1, 2)` | tuple 리터럴 | 불변 리스트. 다중 반환에 자주 사용. |
| `x.get("k", default)` | 안전한 dict 접근 | 키 없으면 default 반환. |
| `**kwargs` | dict unpacking | `f(**{"a":1})` ≡ `f(a=1)`. |
| `*args` | list unpacking | `f(*[1,2])` ≡ `f(1,2)`. |
| `{**a, **b}` | dict 머지 | b가 우선. |
| `[expr for x in xs if cond]` | 리스트 컴프리헨션 | Java stream filter+map. |
| `(expr for x in xs)` | 제너레이터 표현식 | lazy 평가. `sum`, `any`, `all` 등에 자주. |
| `lambda x: x * 2` | 익명 함수 | Java `x -> x * 2`. |
| `f"{x}"` | f-string | 문자열 보간. |
| `r"\\n"` | raw string | 이스케이프 무효화 (regex 패턴 등). |
| `"""다중 줄"""` | triple-quoted | 여러 줄 문자열. |
| `try: ... except E: ...` | 예외 처리 | Java try/catch. |
| `with open(p) as f:` | 컨텍스트 매니저 | Java try-with-resources. |
| `if __name__ == "__main__":` | 모듈 직접 실행 시 | 표준 idiom. |
| `Path("a") / "b"` | 경로 결합 | Pythonic. |
| `enumerate(xs, start=1)` | 인덱스+값 순회 | 1-based 가능. |
| `for k, v in d.items():` | dict 순회 | Java entrySet과 비슷. |
| `dict \| None` (3.10+) | 짧은 Optional | `Optional[dict]`. |

---

## 2. LangGraph 핵심 패턴

```python
from langgraph.graph import START, END, StateGraph

# 1) state schema 선언 (TypedDict)
g = StateGraph(MyState)

# 2) 노드 등록 — 함수의 시그니처는 (MyState) -> dict
g.add_node("a", node_a_fn)
g.add_node("b", node_b_fn)

# 3) 직선 edge
g.add_edge(START, "a")
g.add_edge("a", "b")

# 4) 조건부 edge: router 함수가 다음 노드의 키를 반환
g.add_conditional_edges("b", lambda s: "x" if s["ok"] else "y",
                        {"x": "node_x", "y": "node_y"})

# 5) compile + invoke
runnable = g.compile()
final = runnable.invoke({"k": "v"}, config={"recursion_limit": 50})
```

- 노드 함수의 반환 dict는 **현재 state에 자동 머지**됩니다. `{**state, "key": new}` 패턴을 명시적으로 쓰는 이유는 그게 더 안전하고 읽기 좋아서 (LangGraph 머지 동작에 의존하지 않고 명시적).
- `recursion_limit` — 노드를 통과할 수 있는 최대 횟수. 이걸 안 정하면 무한 루프 시 OOM. IPE에서는 `max(50, max_iter * 12)`로 충분히 잡음.
- **체크포인트**: `g.compile(checkpointer=SqliteSaver(...))` 형태. `runnable.invoke(state, config={"configurable": {"thread_id": run_id}})`로 thread별 영속화. 이후 `runnable.invoke(None, config=...)` 호출이 **resume**.
- **Fan-out / fan-in**: 같은 source에서 여러 `add_edge`로 분기, 같은 target에서 여러 source가 모이면 super-step join. 두 source가 같은 super-step에서 dict를 반환하면 LangGraph가 union 머지 (key 충돌 없으면).

---

## 3. 흔한 실수와 디버깅 포인트

1. **`{**state, "key": v}` 를 안 쓰고 `{"key": v}` 만 반환하면** 기존 state가 다 사라집니다. LangGraph가 머지해주긴 하지만 명시적으로 펼쳐 넣는 게 안전.
2. **`state["key"]` 와 `state.get("key")` 의 차이:** 전자는 키 없으면 KeyError, 후자는 None. 분기 로직에서는 항상 `.get()` 권장.
3. **subprocess의 첫 인자가 문자열** (예: `subprocess.run("ls -la")`)이면 셸을 거치게 되어 인젝션 위험. 항상 리스트로 (`["ls", "-la"]`).
4. **f-string 안에서 중괄호 리터럴**은 `{{` `}}` 로 이스케이프. (Architect/Auditor 프롬프트에서 JSON 예시를 f-string으로 만들 때 유의.)
5. **Path 객체 + 문자열 연산**: `path + "/x"` 는 안 됨. `path / "x"` 가 맞음.
6. **JSON에 한글이 `\uXXXX`로 보이면** `json.dumps(..., ensure_ascii=False)` 빠짐.
7. **`import json` 위치**: 모듈 최상단에. f-string 안에서 `json.dumps(...)`를 호출할 때 import가 누락되면 NameError.

---

## 4. 모듈별 자주 등장하는 Python 관용구

ARCHITECTURE.md의 각 모듈 설명에서 등장한 패턴들을 모듈별로 묶어 정리.

### 4.1 `ipe/llm.py` — Claude 호출 / JSON 파싱

| 패턴 | 의미 |
|---|---|
| `temperature: float \| None = None` | "float 또는 None, 기본값 None". `\|`는 Python 3.10+의 union 표기. |
| `_TEMPERATURE_CAPABLE = {CODER_MODEL}` | 앞에 `_`가 붙은 이름은 "이 모듈 내부용" (privacy 강제 아님). |
| `model in _TEMPERATURE_CAPABLE` | set 멤버십 체크 (Java의 `set.contains(model)`). |
| `**kwargs` | dict를 함수 호출 시 **키워드 인자로 펼치기** (unpack). 매우 자주 쓰는 idiom. |
| `text.find("[", start_idx)` | 문자열에서 `[` 의 위치를 `start_idx`부터 찾기. 없으면 `-1`. |
| `text[i : j+1]` | **슬라이싱**. `i` 인덱스부터 `j` 인덱스까지(끝 미포함) 부분 문자열. |
| `out: list = []` | 빈 리스트 + 명시적 타입 힌트. |

### 4.2 `ipe/graph.py` — LangGraph 라우터

| 패턴 | 의미 |
|---|---|
| `state.get("final_status")` | dict의 안전한 키 접근. 없으면 None. |
| `state.get("iteration_count", 0)` | 키가 없으면 `0` 반환. |
| `failed in ("architect", "coder", ...)` | tuple 멤버십 체크. |
| `_halt`처럼 `_`로 시작하는 함수 | 모듈 내부용. |
| `sum(c.get("cost_usd", 0.0) for c in state.get("llm_calls", []))` | 제너레이터 표현식 + `sum()`. |

### 4.3 `ipe/nodes/architect.py` — 문제 설계자

| 패턴 | 의미 |
|---|---|
| `"""문자열"""` | 여러 줄 문자열 (triple-quoted). 시스템 프롬프트처럼 긴 텍스트. |
| `USER_TEMPLATE.format(algorithm=...)` | 문자열 내 `{algorithm}` 자리에 값 삽입. 템플릿 미리 정의 후 채울 때. |
| `user += "..."` | `user = user + "..."` 의 약어. |
| `{**state, "key": value}` | **dict unpacking**. 기존 state 풀어서 복사 + 추가 키 덮어쓰기. Java의 `new HashMap<>(state); copy.put("key", value);`와 비슷. |
| `chat.invoke([{...}, {...}])` | LangChain의 표준 메시지 형식 (system/user 메시지 리스트). |

### 4.4 `ipe/nodes/coder.py` — 정규식·삼항 표현

| 패턴 | 의미 |
|---|---|
| `re.compile(r"...")` | 정규표현식 컴파일. `r"..."` 는 raw string. |
| `re.DOTALL` | `.` 가 줄바꿈도 매칭하도록 하는 플래그. |
| `(?:...)` | 비캡처 그룹. 그룹화는 하되 결과로 추출 안 함. |
| `(?P<name>...)` | **이름붙은 캡처 그룹**. `match.group("name")`로 추출. |
| `_FENCE_RE.finditer(text)` | 모든 매치를 iterator로 반환. `list(...)`로 즉시 리스트화. |
| `max(matches, key=lambda m: len(m.group(1)))` | `key` 함수로 가장 큰 원소 선택. **lambda**는 한 줄 익명 함수. |
| `impossible_match.group(1).strip() if impossible_match else None` | **삼항 표현식**. Java의 `cond ? a : b` 와 동일하지만 순서가 `값 if 조건 else 값`. |
| `text[: fence.start()]` | 슬라이싱 시작 인덱스 생략 = 0부터. |
| `tuple[str, str \| None]` | "두 원소 튜플 (str, str또는None)" 타입 힌트. |

### 4.5 `ipe/nodes/auditor.py` — 예외 처리

- `try / except`: Java의 `try / catch`. `except (ValueError, KeyError):` 처럼 튜플로 여러 예외 동시 처리.
- `f"Only {len(inputs)} ..."`: f-string으로 변수 삽입.
- 자기 자신을 다시 호출하도록 라우팅하는 패턴 (`last_failed_node="auditor"`)은 LangGraph에서 **자기 루프(self-loop)** 만드는 방법.

### 4.6 `ipe/nodes/generator.py` — 정규식 캡처

- 정규식의 `(?P<name>\S+)` — 이름붙은 캡처 그룹. 매치 후 `m.group("name")` 으로 추출.
- `for m in _BLOCK_RE.finditer(text):` — 매치를 하나씩 순회.
- `list(DEFAULT_SEEDS_PER_GENERATOR)` — 리스트의 **얕은 복사**. 원본을 mutate하지 않으려고. (Java의 `new ArrayList<>(seeds)` 와 비슷.)
- `out.append(...)` — 리스트 끝에 추가 (Java `list.add(...)`).

### 4.7 `ipe/nodes/executor.py` — subprocess·iterator 관용구

| 패턴 | 의미 |
|---|---|
| `for idx, tc in enumerate(samples):` | 인덱스와 값을 동시에 순회. (Java의 `for (int i=0; i<list.size(); i++)` 보다 깔끔.) |
| `n_pass * 2 > len(sample_results)` | "n_pass / total > 0.5" 를 정수 산술로. |
| `any(r["status"] in ("RTE", "TLE") for r in sample_results)` | 제너레이터 표현식 + `any()`. "한 개라도 조건 만족하면 True". |
| `sum(1 for r in sample_results if r["pass"])` | 통과 개수 세기. |
| `[r for r in results if r["phase"] == "sample"]` | **리스트 컴프리헨션** — 필터링한 새 리스트. (Java의 `stream().filter().collect()`.) |
| `uuid.uuid4().hex[:8]` | 무작위 UUID의 처음 8글자만 추출 (디렉토리 이름용). |
| `subprocess.run([...], capture_output=True, text=True, timeout=N)` | 다른 프로세스 실행. 첫 인자가 리스트여야 안전 (셸 인젝션 방지). |
| `proc.stderr or proc.stdout` | Python에서 빈 문자열은 falsy. "stderr 비어있으면 stdout을 써라"는 짧은 idiom. |
| `tuple[bool, str]` | 다중 반환값을 튜플로. |
| `time.perf_counter()` | 고정밀 wall-clock. 시간 측정 표준. |
| `from concurrent.futures import ThreadPoolExecutor, as_completed` | 병렬 실행. subprocess는 GIL 영향 없으므로 thread만으로 충분. |

### 4.8 `ipe/io.py` — 파일 시스템

- `str(i).zfill(width)` — 숫자를 문자열로 바꾸고 width만큼 0으로 좌측 패딩. `1 → "01"`.
- `enumerate(testcases, start=1)` — 인덱스를 1부터 시작.
- `re.sub(r"[^a-zA-Z0-9_-]+", "-", s)` — 정규식 치환 ("알파벳/숫자/_/- 가 아닌 문자" → "-"). 안전한 디렉토리 이름 만들기 (slugify).
- `json.dumps(obj, ensure_ascii=False, indent=2)` — JSON 직렬화. `ensure_ascii=False` 가 있어야 한글이 `\uXXXX` 로 이스케이프 안 됨.
- `Path("a") / "b"` — 경로 결합 (Pythonic). `os.path.join` 대신.
- `path.write_text(content, encoding="utf-8")` — 한 줄에 파일 쓰기.
- `path.symlink_to(target)` — 심볼릭 링크 생성. `outputs/by-name/<alias>` → `<run_id>` 패턴에서 사용.

---

## 5. TypedDict 사용 노트

```python
from typing import TypedDict, List, Dict, Optional

class ProblemState(TypedDict, total=False):
    target_algorithm: str
    iteration_count: int
    ...
```

- **`TypedDict`**: 일반 `dict`인데 키와 타입을 명시적으로 선언한 것. 런타임에는 그냥 dict처럼 동작하지만, 타입 체커(mypy 등)가 잘못된 키 접근을 잡아냄.
  - Java로 비유하면 "필드만 있는 record 클래스" 비슷한 역할이지만, 실제로는 `{"key": value}` dict.
  - `state["problem_title"]` 처럼 접근.
- **`total=False`**: "모든 필드가 있어야 하는 건 아님". 처음에는 `target_algorithm`만 채우고, 노드를 거치면서 점점 다른 필드가 채워지므로 부분적으로 비어있는 상태가 정상.
- **`Optional[str]`**: `str` 또는 `None` 둘 다 허용. `Union[str, None]`의 줄임표현.
- **`Optional[Dict]`**: `Dict` 또는 `None`. Evaluator가 아직 실행되지 않았을 때는 `None`.

---

## 6. 타입 힌트 cheat sheet

| 표기 | 의미 | 예시 |
|---|---|---|
| `int`, `str`, `bool`, `float` | 기본 타입 | `def f(x: int) -> str:` |
| `list[int]` (3.9+) | int 리스트 | `nums: list[int] = []` |
| `dict[str, int]` (3.9+) | str→int 매핑 | `counts: dict[str, int]` |
| `tuple[str, int]` (3.9+) | str+int 튜플 | `pair: tuple[str, int]` |
| `Optional[X]` | `X` 또는 `None` | `name: Optional[str]` |
| `X \| Y` (3.10+) | `X` 또는 `Y` | `id: int \| str` |
| `Literal["a", "b"]` | 리터럴 값만 허용 | `final_status: Literal["success", "halt"]` |
| `Callable[[int, str], bool]` | 함수 타입 | `predicate: Callable[[int, str], bool]` |
| `Any` | 모든 타입 | `data: Any` (가급적 피함) |

---

## 7. 더 학습할 자료

- 공식 Python 튜토리얼: https://docs.python.org/3/tutorial/
- LangGraph 공식 문서: https://langchain-ai.github.io/langgraph/
- TypedDict PEP 589: https://peps.python.org/pep-0589/
- pathlib (Path 객체): https://docs.python.org/3/library/pathlib.html
