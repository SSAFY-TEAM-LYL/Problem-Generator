# IPE 온보딩 가이드 — 처음 보는 사람을 위한 안내서

> 이 문서는 IPE 저장소를 **처음 클론한 사람**이 30분 안에 "무엇인지, 왜 만들었는지, 어떻게 굴러가는지, 어떻게 한 사이클을 직접 돌려보는지"까지 이해하도록 쓰여졌습니다.
>
> 더 깊은 내용을 원하면 마지막 섹션 [다음에 읽을 문서](#10-다음에-읽을-문서)에서 다음 단계를 안내합니다.

---

## 목차

1. [IPE는 무엇인가](#1-ipe는-무엇인가)
2. [왜 만들었나 — 풀려는 문제](#2-왜-만들었나--풀려는-문제)
3. [한눈에 보는 동작 흐름](#3-한눈에-보는-동작-흐름)
4. [6개의 노드 — 누가 무엇을 하나](#4-6개의-노드--누가-무엇을-하나)
5. [핵심 개념 7가지](#5-핵심-개념-7가지)
6. [저장소 디렉토리 구조](#6-저장소-디렉토리-구조)
7. [설치부터 첫 실행까지](#7-설치부터-첫-실행까지)
8. [산출물(outputs/<run_id>/) 읽는 법](#8-산출물outputsrun_id-읽는-법)
9. [자주 마주치는 문제 — Troubleshooting](#9-자주-마주치는-문제--troubleshooting)
10. [다음에 읽을 문서](#10-다음에-읽을-문서)

---

## 1. IPE는 무엇인가

**IPE (Infinite Problem Engine)** 는 **알고리즘 문제를 자동으로 만들어 주는 파이프라인**입니다.

입력은 단 하나, 사용자가 원하는 **알고리즘 카테고리**입니다.

```
입력:  "Two Sum"   |  "Dijkstra"   |  "Segment Tree"   |  "LIS"
        ↓
출력:  problem.md (사람이 읽는 문제)
       problem.json (DB에 그대로 넣을 수 있는 구조화 데이터)
       solution.py (정답 코드)
       generators/*.py (입력 생성기)
       tests/NN.in, NN.out (검증된 테스트 케이스 묶음)
       difficulty 라벨 (Bronze ~ Diamond, 검증 후 사후 측정)
```

즉, **백준이나 SWEA 같은 외부 문제 사이트를 긁어오지 않고**, LLM(Claude)이 문제를 *설계 → 풀이 → 적대적 검증 → 시드 기반 stress test → 난이도 평가*까지 한 번에 끝내고, 그 결과물을 곧바로 코드/문제 DB에 넣을 수 있는 형태로 떨어뜨립니다.

핵심은 두 가지입니다.

- **LangGraph + Claude** 로 구성된 **6개 노드의 그래프**가 단일 상태(`ProblemState`)를 주고받으며 점진적으로 문제를 완성합니다.
- LLM이 만든 코드는 **반드시 격리된 sandbox에서만** 실행됩니다 (Docker / macOS sandbox-exec / RLIMIT 4-tier 자동 선택).

현재 버전: **v0.1.1** (P0~P12 완료 + polish round 3). 자세한 변경 이력은 `CHANGES.md`.

---

## 2. 왜 만들었나 — 풀려는 문제

알고리즘 학습 플랫폼·교육 서비스를 만들려면 "**검증된 문제**" 수천 개가 필요합니다. 그런데 기존 방식에는 다음과 같은 한계가 있습니다.

| 방식 | 한계 |
|---|---|
| 외부 사이트 크롤링 | 저작권/이용약관 위반 위험, 라이선스 정리 비용 |
| 사람이 직접 출제 | 시간·비용·인력 한계, 문제 품질 편차 |
| LLM에 "문제 만들어줘" | 검증 안 됨 — 정답이 틀려도 알 수 없음, 난이도 라벨이 자의적, edge case 미흡 |

IPE는 세 번째를 **자동화된 검증 파이프라인**으로 보완합니다.

- LLM이 문제를 만든다 → **다른 LLM이 정답 코드를 짠다** → **또 다른 LLM이 적대적 입력(edge case)을 만든다** → **샌드박스에서 실제로 코드를 돌려본다** → **모든 케이스가 통과해야** 문제로 인정.
- 통과한 뒤에야 별도의 **Evaluator 노드**가 문제를 풀어 본 흔적(코드 길이, 시간복잡도, 실패 라운드 수)을 근거로 난이도를 **사후 측정**합니다.

→ "LLM이 만들었지만 **검증되었기 때문에 믿을 수 있는**" 문제만 산출물로 떨어집니다.

---

## 3. 한눈에 보는 동작 흐름

```
                    ┌──────────────────────────────────────────────────┐
                    │              IPE 한 사이클(run)                  │
                    └──────────────────────────────────────────────────┘

  사용자 입력
   "Two Sum"
       │
       ▼
  ┌──────────┐      ┌──────────┐      ┌──────────┐
  │Architect │ ───▶│  Coder   │ ───▶│ Executor │ ─── Phase A: 샘플 매칭
  │ (문제 설계)│     │(정답 코드)│     │  3-Phase │
  └──────────┘      └──────────┘      └────┬─────┘
       ▲                ▲                  │
       │                │                  ▼
       │                │            ┌──────────┐
       │                │            │ Decision │ ◀── max_iter / budget / cost guard
       │                │            └────┬─────┘
       │                │                 │
       │                │   ┌─────────────┼─────────────┐
       │                │   │             │             │
       │                │   ▼             ▼             ▼
       │                │  retry        retry         success
       │                │ architect      coder            │
       │                └────────┐                        │
       │                         │                        ▼
       │                  ┌──────────┐  Phase B    ┌──────────┐
       └──────────────────│ Auditor  │ ────────────│Evaluator │ ──▶ END
                          │(엣지케이스)│             │ (난이도) │
                          └──────────┘             └──────────┘
                               ▲
                          Phase C에서 stress test 통과 못하면
                          ┌──────────┐
                          │Generator │ ◀── 시드 기반 입력 생성기
                          └──────────┘
```

위 그림의 핵심을 한 줄씩 풀어 쓰면:

1. **Architect** 가 문제 본문·제약·샘플 3~5개를 만든다.
2. **Coder** 가 그 문제를 푸는 정답 코드를 만든다.
3. **Executor** 가 sandbox에서 코드를 돌려 검증한다.
4. **Decision** 노드가 다음 행동을 결정한다: 성공이면 종료, 실패 원인에 따라 architect / coder / auditor / generator 중 하나로 분기.
5. **Auditor** 는 직접 만든 적대적 입력(코너 케이스)으로 Phase B 검증.
6. **Generator** 는 시드 기반 입력 생성기를 만들어 Phase C에서 다수의 무작위 입력으로 stress test.
7. 모두 통과하면 **Evaluator** 가 난이도(Bronze~Diamond)를 사후 측정하고 종료.

이 흐름은 `ipe/graph.py`에 그대로 코딩되어 있습니다.

---

## 4. 6개의 노드 — 누가 무엇을 하나

각 노드의 책임은 `ipe/nodes/` 디렉토리 한 파일에 격리되어 있습니다. 모든 노드는 같은 시그니처를 따릅니다:

```python
def run(state: ProblemState, *, ...) -> ProblemState:
    ...
```

| 노드 | 파일 | 입력 | 출력 (성공 시 ProblemState에 채워지는 키) |
|---|---|---|---|
| **Architect** | `ipe/nodes/architect.py` | `target_algorithm` | `problem_title`, `problem_description`, `constraints`, `constraints_structured`, `sample_testcases` |
| **Coder** | `ipe/nodes/coder.py` | 위 문제 사양 | `solution_code` |
| **Auditor** | `ipe/nodes/auditor.py` | 문제+정답 | `adversarial_inputs` (코너 케이스 N개) |
| **Generator** | `ipe/nodes/generator.py` | 문제 제약 | `generators` (seed→입력 변환 코드) |
| **Executor** | `ipe/nodes/executor.py` | 위 모든 산출물 | `execution_results`, `testcases`, `final_status` |
| **Evaluator** | `ipe/nodes/evaluator.py` | 검증 끝난 문제 | `difficulty_label`, `difficulty_reasoning`, `difficulty_factors`, `difficulty_calibration_anchors` |

### Executor의 3-Phase

`Executor`만 좀 더 풀어 설명합니다 — 가장 복잡한 노드이고, 다른 노드의 실패를 감지해 적절한 노드로 라우팅하는 책임을 가집니다.

```
Phase A: Architect가 만든 sample 입력 → 정답 코드 실행 → expected와 exact match
         ├─ 모든 sample 통과 → Phase B로
         ├─ 일부만 실패        → "이 문제는 정답 코드가 틀렸나, 입출력이 틀렸나, 제약이 틀렸나"
         │                       를 3-way 휴리스틱으로 판정해 architect / coder 중 하나로 라우팅
         └─ 컴파일 실패        → coder 재시도

Phase B: Auditor가 만든 adversarial input → 정답 코드 실행 → 일관성 확인
         └─ TLE/MLE/RE/WA 발견 시 coder 재시도 (정답 코드의 결함)

Phase C: Generator 코드를 시드 1~K로 호출 → 다수 입력 생성 →
         정답 코드로 정답 산출 → testcases/NN.in, NN.out 저장
         └─ Phase C도 통과해야 final_status="success"
```

Phase C는 `ThreadPoolExecutor`로 병렬 실행됩니다 (`--exec-workers` 로 동시성 조절 가능, 기본 4).

---

## 5. 핵심 개념 7가지

처음 코드를 읽기 전에 알아두면 좋은 7가지 개념입니다.

### 5.1 ProblemState — 모든 노드가 공유하는 단일 dict

`ipe/state.py` 에 `TypedDict`로 정의된 상태 객체. **모든 노드가 이 dict 하나를 받아서, 새 dict를 반환하는 식**으로 동작합니다 (immutable update 패턴).

```python
class ProblemState(TypedDict, total=False):
    run_id: str
    target_algorithm: str
    target_language: str
    iteration_count: int
    max_iter: int
    node_retry_budget: NodeRetryBudget
    max_cost_usd: float | None

    # Architect output
    problem_title: str
    problem_description: str
    sample_testcases: list[dict[str, Any]]
    ...
```

핵심 포인트: `total=False` 이므로 노드를 거치며 **점진적으로 키가 채워지는** 것이 정상입니다. 첫 사이클에서는 `solution_code`가 없고, Coder를 지나면서 채워집니다.

### 5.2 Iteration & Budget — 무한 루프 방지 3중 가드

LLM 파이프라인은 "조금만 더 하면 풀릴 것 같은데..." 하다가 무한 호출되기 쉽습니다. IPE는 세 겹의 가드를 둡니다.

| 가드 | 단위 | 기본값 | 작동 방식 |
|---|---|---|---|
| `max_iter` | 전체 루프 횟수 | 5 | iteration_count가 max_iter에 도달하면 `max_iterations`로 종료 |
| `node_retry_budget` | **노드별** 재시도 | architect=2, coder=4, auditor=4, generator=2 | 특정 노드가 budget을 다 쓰면 `budget_exhausted`로 종료 |
| `max_cost_usd` | 누적 API 비용 | 5.0 USD | 누적 토큰 비용이 한도를 넘으면 `cost_exceeded`로 종료 |

이 가드는 `ipe/graph.py::_decision` 노드에서 매 사이클마다 평가됩니다.

### 5.3 4-tier Sandbox — LLM 코드를 안전하게 돌리는 법

LLM이 만든 코드를 그대로 `python solution.py` 로 돌리면 위험합니다 (파일 시스템 접근, 무한 루프, OOM). IPE는 환경에 따라 자동으로 격리 강도를 고릅니다.

| Tier | 메커니즘 | 가용 환경 | 격리 강도 |
|---|---|---|---|
| **T1** | Docker container | Docker Desktop 설치된 곳 | 강 (네트워크 차단, FS readonly) |
| **T2** | nsjail (미구현, 자리 차지) | Linux only | 강 |
| **T2.5** | macOS `sandbox-exec` | macOS | 중 (FS write 제한) |
| **T3** | `resource.setrlimit` + subprocess | 모든 POSIX | 약 (CPU/MEM/FD 제한만) |

선택 로직은 `ipe/sandbox/selector.py::pick_runner`에 있고, `--sandbox auto` (기본) 이면 위에서 아래로 시도해 첫 가용 tier를 씁니다. 강제는 `--sandbox docker` 같이 가능. 격리 자체가 동작하는지는 `make selftest-all` 로 확인할 수 있습니다.

### 5.4 LangGraph — 그래프 그 자체

[LangGraph](https://github.com/langchain-ai/langgraph)는 LangChain 팀이 만든 *상태 기반 워크플로 엔진*입니다.

- **노드** = `(state) -> state` 함수
- **엣지** = 노드 간 전이 (조건부 분기 가능)
- **체크포인터** = 각 super-step 결과를 영속화 (여기서는 SqliteSaver 사용)

`ipe/graph.py::build_graph`가 6개 노드와 1개 decision 노드를 엮어서 컴파일된 그래프를 반환합니다. main.py는 `graph.invoke(initial_state, config)` 한 줄로 전체 사이클을 돌립니다.

### 5.5 Resumable & Replayable — 두 가지 재실행 모드

| 모드 | 명령 | 무엇을 다시 하나 | LLM 호출 발생? |
|---|---|---|---|
| **새 run** | `python main.py --algorithm "Two Sum"` | 처음부터 | 예 (비용 발생) |
| **resume** | `python main.py --resume <run_id>` | 크래시 직전 super-step부터 이어서 | 예 (이어지는 만큼) |
| **replay** | `python main.py --replay <run_id>` | LLM 호출은 `llm_traces/`에서 읽어 재현 | **0** (비용 0) |

- `resume`은 도중에 프로세스가 죽었을 때 복구용. `outputs/<run_id>/checkpoint.db`가 있어야 동작.
- `replay`는 디버깅/회귀 테스트용. 모든 LLM 호출이 `outputs/<run_id>/llm_traces/<seq>_<node>.json`에 raw로 저장되어 있고, `ReplayTracker`가 이를 그대로 되돌려줍니다. 비결정성이 사라지므로 같은 결과가 재현됩니다.

### 5.6 Calibration Anchor — 난이도 평가의 "기준점"

LLM이 그냥 "이 문제는 Gold" 라고 말하면 신뢰할 수 없습니다. IPE는 `ipe/calibration/anchors.json` 에 미리 알려진 난이도의 문제들(예: BOJ 1000 = Bronze V, BOJ 11401 = Diamond IV)을 **anchor**로 제공해, Evaluator가 새 문제를 anchor와 비교하도록 합니다. 출력물에는 사용된 anchor들이 `difficulty_calibration_anchors`에 동봉됩니다 → 사람이 사후 검수할 때 비교 기준이 됩니다.

### 5.7 LLM 호출은 모두 추적된다 (Observability)

`ipe/observability.py::LLMCallTracker`는 모든 LLM 호출에 대해:

- **seq** (전역 순번)
- **node** (어느 노드에서 호출했는지)
- **model**, **input_tokens**, **output_tokens**, **cost_usd**, **timestamp**
- **raw trace** (`outputs/<run_id>/llm_traces/0001_architect.json` 형식)

을 기록합니다. 이는 `ProblemState["llm_calls"]` 리스트에도 누적되고, 이 누적 비용이 매 `decision` 노드에서 `max_cost_usd`와 비교됩니다.

P11에서는 **structured JSON 로깅** (`ipe/logging_config.py`) + **LangSmith / OpenTelemetry export** (`ipe/_tracing.py`) 가 추가됐습니다. `.env`의 `IPE_LANGSMITH=1` 또는 `IPE_OTEL_ENDPOINT=...` 로 활성화됩니다.

---

## 6. 저장소 디렉토리 구조

```
IPE/
├─ README.md                ← 짧은 진입 페이지
├─ CHANGES.md               ← 변경 이력 (Round 1~23 + RFC + Catalog + Baseline)
├─ docs/
│  ├─ ONBOARDING.md         ← (이 문서) 처음 보는 사람을 위한 가이드
│  ├─ SPEC.md               ← 요구사항·기술 스택·인수 기준 SSOT
│  ├─ ARCHITECTURE.md       ← 모듈별 코드 설계 + 운영 가드레일
│  ├─ PRINCIPLES.md         ← 5 운영 룰 (measurement / regression / baseline / complexity / rollback)
│  ├─ improvements/         ← 통합 RCA 5 + 단독 3
│  ├─ baseline/             ← measurement (N=3 보고서 + raw data)
│  ├─ catalog/              ← Catalog JSONL schema
│  └─ archive/              ← 한시 문서 + 원본 RCA + RFC + backlog + dev guides
│
├─ main.py                  ← CLI 진입점 (argparse + graph.invoke)
├─ pyproject.toml           ← 패키지 메타 + ruff/mypy/pytest 설정
├─ requirements.txt         ← (참고용; 실제 설치는 pyproject 사용)
├─ Makefile                 ← install / lint / test / ci / selftest / clean
├─ Dockerfile               ← T1 sandbox용 base image
├─ .env.example             ← 환경 변수 템플릿 (복사해 .env로 사용)
├─ .pre-commit-config.yaml  ← commit 시 ruff 자동 실행
│
├─ ipe/                     ← 소스 패키지 (편집 시 가장 자주 들어가는 곳)
│  ├─ __init__.py
│  ├─ state.py              ← ProblemState (TypedDict) — 모든 노드가 공유
│  ├─ graph.py              ← LangGraph 빌더 + decision 노드 + 라우팅
│  ├─ llm.py                ← Claude 클라이언트 wrapper + JSON 파서
│  ├─ io.py                 ← outputs/<run_id>/ 산출물 직렬화
│  ├─ _io_render.py         ← problem.md / generators / tests 렌더링
│  ├─ observability.py      ← LLMCallTracker / ReplayTracker
│  ├─ logging_config.py     ← structured JSON 로깅 (P11)
│  ├─ _tracing.py           ← LangSmith / OTel toggle (P11.3 / F4)
│  │
│  ├─ nodes/                ← 6개 노드 + executor 내부 헬퍼
│  │  ├─ architect.py
│  │  ├─ coder.py
│  │  ├─ auditor.py
│  │  ├─ generator.py
│  │  ├─ executor.py
│  │  ├─ evaluator.py
│  │  ├─ _executor_helpers.py   ← workdir/컴파일/실행
│  │  ├─ _executor_phases.py    ← Phase B / Phase C 본체
│  │  └─ _history.py            ← iteration_history → prompt 섹션
│  │
│  ├─ sandbox/              ← 4-tier 격리 실행기
│  │  ├─ runner.py          ← SandboxedRunner Protocol
│  │  ├─ docker_runner.py        (T1)
│  │  ├─ sandboxexec_runner.py   (T2.5, macOS)
│  │  ├─ rlimit_runner.py        (T3, fallback)
│  │  ├─ selector.py        ← pick_runner(strategy)
│  │  └─ __main__.py        ← `python -m ipe.sandbox` 자가진단 CLI
│  │
│  └─ calibration/
│     └─ anchors.json       ← 난이도 anchor (Bronze~Diamond 대표 문제들)
│
├─ tests/                   ← 210 tests, coverage 93%
│  ├─ test_state.py / test_llm.py / test_observability.py / ...
│  ├─ sandbox/test_isolation.py
│  ├─ integration/          ← end-to-end 미니회로 / phase별 / replay / resume
│  └─ e2e/test_smoke.py     ← `-m "not e2e"`로 평소엔 제외, 수동 트리거
│
├─ outputs/                 ← run당 한 디렉토리 (gitignored)
│  └─ <run_id>/
│     ├─ problem.json / problem.md
│     ├─ solution.py
│     ├─ generators/*.py
│     ├─ tests/NN.in, NN.out + manifest.json
│     ├─ llm_traces/<seq>_<node>.json
│     └─ checkpoint.db
│
├─ archive/                 ← 외부 리뷰 등 archival 문서
├─ docs/backlog/            ← post-P3 백로그
├─ docs/improvements/       ← 개선 노트
└─ .github/                 ← CI workflow
```

---

## 7. 설치부터 첫 실행까지

### 7.1 사전 요구사항

- **macOS 또는 Linux** (Windows는 WSL2 권장)
- **Python 3.11+** — `brew install python@3.11` (macOS) 또는 `apt install python3.11`
- **Anthropic API 키** — https://console.anthropic.com/ 에서 발급 (유료, 한 사이클 약 $0.5~$3)
- **(선택) Docker Desktop** — sandbox T1 사용 시. 없으면 T2.5/T3로 자동 fallback

### 7.2 설치 (4단계)

```bash
# 1. 가상환경 생성 + activate
python3.11 -m venv .venv
source .venv/bin/activate

# 2. 패키지 + dev 의존성 설치 (editable 모드)
make install
# 또는: pip install -e ".[dev]"

# 3. 환경 변수 셋업
cp .env.example .env
# .env를 열어 ANTHROPIC_API_KEY=sk-ant-... 입력

# 4. (선택) pre-commit hooks — git commit 시 ruff 자동 실행
pre-commit install
```

### 7.3 검증 — 코드가 정상인지

설치가 끝났으면 LLM을 호출하지 않는 단위 테스트로 환경을 검증합니다.

```bash
make ci          # ruff + mypy --strict + pytest (with coverage)
```

여기까지 통과해야 다음 단계로 갑니다. 210개 테스트가 모두 통과하고 coverage 93% 이상이 나와야 정상입니다.

추가로 sandbox 격리가 진짜 동작하는지도 확인:

```bash
make selftest         # 자동 선택된 tier 자가진단
make selftest-all     # 가용한 모든 tier 자가진단
```

### 7.4 첫 사이클 — LLM 호출이 일어나는 실제 실행

```bash
# Two Sum 문제를 하나 만들어 본다 (약 1~3분, $0.3~$1.5)
python main.py --algorithm "Two Sum" --language python --max-iter 5 --max-cost-usd 2.0
```

성공하면 다음과 같은 흐름이 stderr/stdout에 보입니다:

```
=== IPE run_id=a3f29b18e0c4 algo='Two Sum' lang=python (sandbox=sandboxexec) ===
[INFO] architect: problem designed (title='두 수의 합')
[INFO] coder: solution generated (12 lines)
[INFO] executor: Phase A 3/3 samples passed
[INFO] auditor: 5 adversarial inputs generated
[INFO] executor: Phase B 5/5 passed
[INFO] generator: 2 generators created
[INFO] executor: Phase C 20/20 passed
[INFO] evaluator: difficulty=Silver IV (anchors=[BOJ 1000, BOJ 2750])

=== final_status=success ===
{
  "run_id": "a3f29b18e0c4",
  "final_status": "success",
  "iteration_count": 1,
  "problem_title": "두 수의 합",
  "execution_results": [...],
  "llm_calls_count": 6
}
```

종료 코드는 `final_status=="success"` 이면 0, 그 외(`max_iterations`, `budget_exhausted`, `cost_exceeded`)이면 1입니다.

### 7.5 결과 확인

`outputs/<run_id>/` 디렉토리를 열어 보면 [§8](#8-산출물outputsrun_id-읽는-법)에서 설명하는 구조로 산출물이 떨어져 있습니다.

### 7.6 자주 쓰는 CLI 옵션

```bash
# 언어를 자바로
python main.py --algorithm "Dijkstra" --language java

# sandbox를 강제로 지정 (Docker가 있어도 rlimit로)
python main.py --algorithm "BFS" --sandbox rlimit

# 노드별 retry budget 변경
python main.py --algorithm "LIS" \
  --budget-architect 3 --budget-coder 6 --budget-auditor 6 --budget-generator 3

# Phase C 병렬도 조절
python main.py --algorithm "Segment Tree" --exec-workers 8

# 도중에 죽었으면 이어서
python main.py --resume a3f29b18e0c4

# 같은 결과를 LLM 비용 없이 재현
python main.py --replay a3f29b18e0c4
```

전체 옵션은 `python main.py --help`.

---

## 8. 산출물(outputs/<run_id>/) 읽는 법

성공한 run 하나는 다음과 같이 떨어집니다.

```
outputs/a3f29b18e0c4/
├─ problem.json          ← DB-insertable. title, description, constraints, samples 등
├─ problem.md            ← 사람이 읽는 형태 (markdown)
├─ solution.py           ← Coder가 만든 정답 코드
├─ generators/
│  ├─ small_dense.py     ← seed → 입력 변환기 (Phase C에서 사용)
│  └─ large_sparse.py
├─ tests/
│  ├─ 01.in / 01.out     ← sample testcase 1
│  ├─ 02.in / 02.out
│  ├─ 03.in / 03.out
│  ├─ 04.in / 04.out     ← adversarial (Auditor 산출)
│  ├─ 05.in / 05.out
│  ├─ 06.in / 06.out     ← generator로 생성된 stress test
│  ├─ ...
│  └─ manifest.json      ← 각 케이스의 출처(sample/adv/gen) + seed
├─ llm_traces/
│  ├─ 0001_architect.json
│  ├─ 0002_coder.json
│  ├─ 0003_auditor.json
│  ├─ ...
│  └─ 0006_evaluator.json
└─ checkpoint.db         ← SqliteSaver — resume용 (이미 끝난 run에서는 무의미)
```

또한 `outputs/by-name/<timestamp>_<algo>/` 는 위 디렉토리에 대한 사람 친화적인 심볼릭 링크 (예: `2026-05-14_two_sum → ../a3f29b18e0c4`) 로, 나중에 사람이 찾아볼 때 편합니다.

### 무엇을 어디에 쓰나

| 용도 | 보는 파일 |
|---|---|
| 문제를 사람이 읽고 검수 | `problem.md` |
| 문제를 DB에 적재 | `problem.json` (스키마는 `SPEC.md §6`) |
| 정답 코드의 품질 검수 | `solution.py` |
| 채점 시스템에 import | `tests/*.in`, `tests/*.out` (백준 호환 포맷) |
| LLM이 정말 그렇게 답했는지 감사 | `llm_traces/*.json` |
| run을 재현 / 회귀 테스트 | `--replay <run_id>` |

---

## 9. 자주 마주치는 문제 — Troubleshooting

### 9.1 `KeyError: 'ANTHROPIC_API_KEY'`

`.env` 파일이 없거나 키가 비어 있습니다. `cp .env.example .env` 후 `ANTHROPIC_API_KEY=sk-ant-...` 입력.

### 9.2 `RuntimeError: no usable sandbox tier`

어떤 tier도 자가진단을 통과하지 못한 상황. `make selftest-all`로 어느 tier가 죽었는지 확인하고, 최후엔 `--sandbox rlimit`을 강제하면 거의 항상 동작합니다.

### 9.3 `final_status: cost_exceeded` 가 즉시 떨어진다

`--max-cost-usd`가 너무 작거나 (예: 0.1) Architect/Coder의 prompt가 큰 케이스. 기본 5.0 USD에서 시작하고, 토큰이 큰 알고리즘(예: Suffix Array)은 10.0 USD까지 늘려도 안전합니다.

### 9.4 `final_status: budget_exhausted`

어떤 노드가 retry budget을 다 썼습니다. `--budget-coder 6` 처럼 늘려서 재시도. 그래도 안 풀리면 LLM이 이 알고리즘 카테고리를 잘 못 다루는 신호 — `iteration_history`(state)나 `llm_traces/`를 열어 어디서 막혔는지 확인.

### 9.5 `checkpoint not found: outputs/<run_id>/checkpoint.db`

`--resume` 대상이 첫 super-step 전에 죽어서 SqliteSaver가 무엇도 저장하지 못한 경우, 또는 run_id를 잘못 적은 경우. `ls outputs/`로 실제 run_id 확인 후 재시도, 또는 새 run을 시작.

### 9.6 `mypy --strict` 실패

새 노드/함수 추가 시 모든 시그니처에 type annotation이 필요합니다. LangGraph 노드는 정확히 `(state: ProblemState) -> ProblemState` 형태여야 합니다.

### 9.7 테스트는 통과하는데 실제 run이 이상하다

- `tests/`는 LLM을 mocking합니다 (`-m "not e2e"` 기본). 실제 LLM 출력이 우리 파서가 가정한 형식과 다르면 실패 — `llm_traces/<seq>_<node>.json`의 raw response를 열어 비교.
- `tests/e2e/test_smoke.py`는 실제 LLM을 부르므로 비용이 듭니다. CI에선 자동 실행 안 됨, 수동으로 `pytest -m e2e`.

더 자세한 운영 가드는 [`ARCHITECTURE.md` §7-10](ARCHITECTURE.md).

---

## 10. 다음에 읽을 문서

여기까지 따라왔다면 다음 단계는 관심사에 따라 다릅니다.

| 관심사 | 다음에 볼 문서 |
|---|---|
| "이 시스템이 *왜* 이렇게 설계됐는지 알고 싶다" | [`SPEC.md`](SPEC.md) — 요구사항·기술 스택·인수 기준 SSOT |
| "각 모듈이 *어떻게* 구현됐는지 알고 싶다" | [`ARCHITECTURE.md`](ARCHITECTURE.md) — 모듈별 설계 + 운영 가드 |
| "운영 룰 / measurement gate" | [`PRINCIPLES.md`](PRINCIPLES.md) — 5 운영 룰 SSOT |
| "단계별 구현 순서와 DoD를 보고 싶다" | [`archive/dev/IMPLEMENTATION_ROADMAP.md`](archive/dev/IMPLEMENTATION_ROADMAP.md) — P0~P12 (역사적) |
| "Python/LangGraph 문법이 낯설다" | [`archive/dev/PYTHON_GUIDE.md`](archive/dev/PYTHON_GUIDE.md) — 본 프로젝트에서 쓰는 관용구 (역사적) |
| "최근에 무엇이 바뀌었나" | [`../CHANGES.md`](../CHANGES.md) — Round 1~23 + Catalog + Baseline 통합 변경 이력 |
| "측정 데이터 (단일 LLM vs IPE)" | [`baseline/v0.3.0-rc1-N3.md`](baseline/v0.3.0-rc1-N3.md) |
| "코드에 기여하려 한다" | `make ci`로 lint+test 통과 → `tests/`에 새 테스트 추가 → PR 발행. PRINCIPLES.md 룰 1~5 준수 |

### 코드에 손대기 전 권장 순서

1. `ipe/state.py` 를 정독한다 — 전체 데이터 모델이 여기 다 있다.
2. `ipe/graph.py` 를 정독한다 — 흐름과 분기 로직이 한 파일에 응축돼 있다.
3. `ipe/nodes/architect.py` 한 노드만 깊게 본다 — 모든 노드가 같은 패턴.
4. `ipe/nodes/executor.py` + `_executor_phases.py` 를 본다 — 가장 복잡하고 가장 가치 있는 노드.
5. `tests/integration/test_minimal_circuit.py` 를 본다 — 노드들이 어떻게 엮여 돌아가는지 미니회로로 확인.

---

## 부록 — 한 줄 요약 모음

- **무엇**: LLM이 알고리즘 문제를 *설계 → 풀이 → 적대적 검증 → stress test → 난이도 평가*까지 자동으로 만들어 주는 파이프라인.
- **왜**: 외부 크롤링 없이, 자의적 LLM 출력 없이, **검증된** 문제만을 자동 생산하기 위해.
- **어떻게**: LangGraph 위의 6노드 그래프가 `ProblemState` 단일 dict를 주고받으며, sandbox에서 코드를 실행해 검증.
- **얼마나 안전**: 4-tier sandbox + iteration/budget/cost 3중 가드 + checkpointing + replay.
- **얼마나 검증됨**: 210 tests, coverage 93%, mypy --strict, ruff clean.
- **현재 버전**: v0.1.1 — P0~P12 + polish round 3 완료.
