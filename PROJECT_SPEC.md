# 🚀 프로젝트 명세서: Infinite Problem Engine (IPE) - MVP Test Edition
**문서 목적:** 실제 프로덕트 도입 전, LangGraph와 Claude 모델만을 활용하여 문제 생성·검증·난이도 평가 파이프라인의 MVP(Minimum Viable Product) 가능성을 테스트하기 위한 기술 명세.

---

## 1. 프로젝트 핵심 목표 및 전제
* **자립형 파이프라인 (Self-Sustaining Pipeline):** 외부 문제 소스(백준 등)에 의존하지 않고, 고품질의 알고리즘 문제(SWEA B형, 백준 골드 수준 포함)를 자체 생산.
* **Claude-Exclusive Stack:** 모델 간의 문맥 이해도와 논리적 일관성을 극대화하기 위해 전 노드에 Claude 제품군(Claude Opus 4.7, Sonnet 4.6 등)을 적용.
* **Local-First Verification:** 백엔드(Spring/DB) 연결 전, 로컬 OS 환경(Python Subprocess)에서 컴파일 및 런타임 검증을 수행하여 에이전트 피드백 루프의 무결성을 최우선으로 테스트.
* **Sandboxed Local Execution:** LLM이 생성한 솔루션·제너레이터 스크립트는 **반드시 격리된 환경**에서 실행. 메모리·CPU·파일시스템·네트워크를 모두 통제하여 호스트 안정성과 보안을 유지. (§4.5.1 참조)
* **Cross-Platform Target (Q2 결정):** MVP는 **Linux / macOS / Windows** 모두 지원. 운영(CI/Production) 환경은 **Docker(T1) 강제 권장**. macOS/Windows 개발 환경은 Docker Desktop 사용을 권장하되, 부재 시 OS별 fallback (macOS → T2.5 sandbox-exec, Windows → T3 + 경고). 사용자 개발 OS = macOS 가정 (§4.5.1 OS별 자동 선택 표 참조).
* **LangGraph Native (Q1 결정):** 워크플로 오케스트레이션은 LangGraph로 구현. ECC 통합(MCP tool 노출 등)은 future 확장으로 분리.
* **Post-Verification Difficulty Rating:** 난이도는 사전 지정이 아닌, 문제 생성·검증이 완료된 후 별도 에이전트가 문제의 구조·알고리즘·제약조건을 분석하여 사후 측정. **Calibration anchor set**(백준 표준 난이도별 샘플)을 프롬프트에 동봉하여 분산을 줄임.
* **Resumable & Observable:** LangGraph checkpointer로 노드 단위 상태를 지속화하여 실패 시 resume 가능. 모든 LLM 호출·비용·실행 결과는 trace로 영속화하여 재현/디버깅 가능.
* **Single-to-Multi 아키텍처:** 현재는 각 단계를 단일 에이전트가 수행하지만, 노드 인터페이스와 State 구조를 열어두어 향후 하위 에이전트(Sub-agents) 오케스트레이션 또는 **병렬 분기(Auditor‖Generator)** 로 즉시 전환 가능하도록 설계.

---

> **구현 로드맵**: 본 명세를 sprint/task로 분해한 12-phase 로드맵은 [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md)에 별도 문서로 정의됨. planner 에이전트는 그 문서를 참조하여 ticket 단위로 분해 가능.

## 1.5 Design Decisions (Q1~Q5 결정 — REVIEW_REPORT 기반)

| # | 질문 | 결정 | 근거 |
|---|---|---|---|
| **Q1** | LangGraph 유지? | **유지** | 이미 SqliteSaver/conditional_edges/recursion_limit 설계 완료. ECC 통합은 future. |
| **Q2** | 타겟 OS? | **Cross-platform** (Linux/macOS/Windows). Docker(T1) 권장, OS별 fallback 명시. | 사용자 개발 환경 macOS, 운영은 Linux. Docker Desktop을 권장 의존성으로. |
| **Q3** | Python 교육 콘텐츠 분리? | **분리 ([`PYTHON_GUIDE.md`](PYTHON_GUIDE.md))** | CLI 에이전트 컨텍스트 효율 (~250줄 절약). |
| **Q4** | `problem.json` 스키마 SSOT? | **본 문서 (`PROJECT_SPEC.md`) §6** | ARCHITECTURE.md §6는 DB 매핑 관점만 다룸. |
| **Q5** | Retry budget 조정? | **coder 3→4, max_iter 5→7** | TLE↔다른에러 핑퐁 케이스 흡수, 글로벌이 노드 합을 무력화 안 하도록. |

각 결정의 상세 영향 범위는 §1, §4, §5, §6에 반영되어 있다.

---

## 2. Global State Schema (상태 관리 구조)
LangGraph 내에서 에이전트 간 공유되는 `ProblemState` 설계. 향후 Sub-agent 들이 참조할 수 있도록 세분화된 컨텍스트를 포함합니다.

```python
from typing import TypedDict, List, Dict, Optional, Literal

class ConstraintSpec(TypedDict, total=False):
    # 구조화된 제약조건 — Executor가 problem별 timeout/memlimit을 enforce 가능하도록.
    variables: List[Dict]      # [{name: "N", min: 1, max: 100000, type: "int"}]
    time_limit_ms: int         # ex: 2000 (기본 5000)
    memory_limit_mb: int       # ex: 256 (기본 512)
    raw: str                   # 자유 서술 원문 (사람용)

class IterationRecord(TypedDict, total=False):
    iter_index: int
    node: str                  # "architect" | "coder" | ...
    action: str                # "regenerate" | "fix" | "extend" ...
    error_signature: str       # 짧은 해시 가능한 실패 요약
    feedback: str

class LLMCallRecord(TypedDict, total=False):
    seq: int
    node: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: str             # ISO 8601
    trace_path: str            # outputs/<run>/llm_traces/<seq>.json

class NodeRetryBudget(TypedDict, total=False):
    architect: int             # 기본 2
    coder: int                 # 기본 3
    auditor: int               # 기본 2
    generator: int             # 기본 2

class ProblemState(TypedDict, total=False):
    # 1. Meta Info (입력)
    run_id: str                # uuid — checkpointer/trace 식별자
    target_algorithm: str      # ex: "Dijkstra", "Segment Tree"
    target_language: str       # "java" or "python"
    iteration_count: int       # 현재 재시도 횟수 (글로벌)
    max_iter: int              # 최대 재시도 횟수 (기본 5, 안전망)
    node_retry_budget: NodeRetryBudget   # 노드별 잔여 재시도 횟수
    max_cost_usd: Optional[float]        # 비용 가드 (기본 5.0)

    # 2. Architect Output
    problem_title: str
    problem_description: str   # Markdown 포맷의 문제 지문
    constraints: str           # 자유 서술 (legacy, 사람용)
    constraints_structured: ConstraintSpec  # 신규 — Executor enforce용
    sample_testcases: List[Dict]  # 3~5개의 손검증 가능한 작은 예제
    has_special_judge: bool             # multiple-valid-output 문제 여부
    special_judge_code: Optional[str]   # checker.py — Phase A에서 stdout 비교 대신 사용

    # 3. Coder Output
    solution_code: str         # Java 또는 Python 정해 코드

    # 4. Auditor Output
    adversarial_inputs: List[Dict]  # 8~15개의 소규모 적대적 엣지케이스
    # [{input, category, reason}] — expected_output은 Executor가 oracle로 채움
    # input은 Executor 사전검증(constraints_structured와 일치하는지)을 통과해야 함

    # 5. Generator Output
    generators: List[Dict]     # 시드 기반 Python 스크립트 3~5개
    # [{name, category, code, seeds, description}]

    # 6. Executor Output
    testcases: List[Dict]      # 전체 최종 테스트케이스 (sample + adversarial + generated)
    execution_results: List[Dict]  # 각 케이스별 실행 결과
    feedback_message: Optional[str]    # 실패 시 해당 노드에 전달되는 피드백
    last_failed_node: Optional[str]    # 실패 시 라우팅 대상 노드
    final_status: Optional[Literal["success", "max_iterations", "budget_exhausted", "cost_exceeded"]]

    # 7. Iteration / Observability (전 노드 공통)
    iteration_history: List[IterationRecord]  # 시도 이력 — feedback에 동봉되어 oscillation 방지
    llm_calls: List[LLMCallRecord]            # LLM 호출 누적 + 비용 추적

    # 8. Difficulty Evaluator Output (검증 완료 후)
    difficulty_label: Optional[str]     # ex: "Gold 3", "Silver 1"
    difficulty_reasoning: Optional[str] # 난이도 판정 근거
    difficulty_factors: Optional[Dict]  # 세부 평가 요소 (알고리즘 복잡도, 구현 난이도 등)
    difficulty_calibration_anchors: Optional[List[Dict]]  # 사용된 anchor 샘플 ID 목록
```

> **`target_difficulty`는 입력에 존재하지 않습니다.** 난이도는 Executor 검증 통과 후 Difficulty Evaluator가 사후 산정합니다.

> **재시도 제어는 두 단계입니다.** `iteration_count` (글로벌, 안전망) + `node_retry_budget` (노드별, 정밀 제어). 글로벌이 도달하기 전에 어떤 노드든 자기 budget이 0이 되면 즉시 `final_status="budget_exhausted"`로 종료.

---

## 3. 파이프라인 아키텍처

```
사용자 CLI (main.py)
        │ (target_algorithm, target_language)
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
        ▼ (adversarial_inputs : 8~15개 소규모 엣지케이스)
 ┌──────────────┐
 │  Generator   │
 └──────┬───────┘
        ▼ (generators : 시드 기반 Python 스크립트 3~5개)
 ┌──────────────┐
 │   Executor   │  Phase A → B → C (3-Phase 검증)
 └──────┬───────┘
        ▼ 조건부 분기 (route_after_executor)
   ┌────┴────┐
   │ success │── Difficulty Evaluator → END (산출물 저장)
   │ coder   │── 다시 Coder로
   │ auditor │── 다시 Auditor로
   │ generator│── 다시 Generator로
   │ architect│── 다시 Architect로
   │ halt    │── max_iter 초과 시 종료
   └─────────┘
```

---

## 4. 노드별 역할 및 MVP 프롬프트 전략

> **모델 식별자**: 본 섹션은 사람이 읽기 쉽도록 마케팅명(예: "Claude Opus 4.7")을 사용한다. 코드/설정/trace에서 사용할 **API ID**는 [`ARCHITECTURE.md §3.3.0`](ARCHITECTURE.md#330-모델명--api-id-표준-매핑-ssot) 매핑 표를 단일 진실원으로 한다 (REVIEW_REPORT M2).

### 📌 Node 1: [The Architect] - Problem Designer
* **사용 모델:** Claude Opus 4.7
* **핵심 역할:** 요청된 알고리즘 유형에 맞는 창의적인 지문 및 제약 조건 생성. **난이도는 지정하지 않고, 알고리즘 특성에 충실한 문제를 자유롭게 설계.**
* **입력:** `target_algorithm` (+ 실패 시 `feedback_message`, `iteration_history`)
* **출력:** `problem_title`, `problem_description`, `constraints` (자유 서술 원문), `constraints_structured` (Executor enforce용 구조화 객체), `sample_testcases` (3~5개, N ≤ 5 수준의 손검증 가능 크기), `has_special_judge` (boolean)
* **MVP 체크포인트:**
    * 단순 복제가 아닌 고유한 스토리텔링 적용.
    * 입력 데이터 범위($N, M$)와 시간 제한의 상관관계가 논리적으로 모순이 없는지 검토.
    * 각 sample_testcase에 `expected_output`과 `note`(풀이 과정 힌트) 포함.
    * **`constraints_structured` 필수 출력**: `variables`(name/min/max/type), `time_limit_ms`, `memory_limit_mb`. raw 문자열만 출력하면 Executor가 글로벌 5초/512MB 기본값으로 fallback하지만 **재시도(feedback)** 가 강제됨.
    * `has_special_judge=true`일 경우 다음 사이클에서 SpecialJudge 노드가 활성화 (P2 — Future).
* **확장성:** 추후 `Story_Agent`와 `Constraint_Agent`로 분리될 것을 대비해, 지문과 제약조건을 명확히 구분하여 출력하도록 강제.

### 📌 Node 2: [The Coder] - Solution Master
* **사용 모델:** Claude Sonnet 4.6 (코드 생성 특화) 또는 Claude Opus 4.7
* **핵심 역할:** 지문을 만족하는 최적 성능의 정해(Golden Solution) 작성.
* **입력:** `problem_description`, `constraints`, `target_language` (+ 실패 시 `feedback_message`)
* **출력:** `solution_code` (펜스 코드 블록 형식)
* **MVP 체크포인트:**
    * Java의 경우 `BufferedReader`, `StringTokenizer` 등을 활용한 PS 최적화 코드 작성.
    * 시간 복잡도 제한 내에서 동작하는지 스스로 주석을 달아 증명.
    * 문제가 본질적으로 풀 수 없는 경우 `IMPOSSIBLE: <reason>` 접두사로 명시 → Architect로 라우팅.
* **확장성:** 추후 언어별 전담 에이전트(`Java_Agent`, `Python_Agent`)가 병렬로 코드를 작성하고 상호 검증하는 구조로 확장.

### 📌 Node 3: [The Auditor] - Adversarial Testcase Generator
* **사용 모델:** Claude Opus 4.7
* **핵심 역할:** 정해 코드와 지문을 기반으로 **소규모(입력 ≤200자) 적대적 엣지케이스** 8~15개 도출. (`expected_output`은 생성하지 않음 — Executor가 솔루션을 oracle로 사용하여 채움.)
* **입력:** `problem_description`, `constraints`, `solution_code` (+ 실패 시 `feedback_message`)
* **출력:** `adversarial_inputs` — `[{input, category, reason}]`
* **카테고리:** `MIN_SIZE`, `SINGLE_ELEMENT`, `UNIFORM`, `BOUNDARY_LOW/HIGH`, `SORTED_ASC/DESC`, `DEGENERATE`, `NUMERICAL_EDGE`, `ADVERSARIAL`
* **MVP 체크포인트:**
    * 경계값(최댓값/최솟값, 빈 배열, 사이클이 존재하는 그래프 등)을 반드시 포함.
    * 각 테스트케이스가 어떤 취약점을 검증하기 위함인지 명시(`reason` 필드).
    * 최소 8개 미만 시 자기 자신에게 재요청 (`last_failed_node: "auditor"`).

### 📌 Node 4: [The Generator] - Seed-Based Input Script Writer
* **사용 모델:** Claude Opus 4.7
* **핵심 역할:** **Codeforces Polygon 패턴**을 따라, 시드를 인자로 받아 대규모 입력을 결정론적으로 생성하는 Python 스크립트 3~5개 작성.
* **입력:** `problem_description`, `constraints`, `solution_code` (+ 실패 시 `feedback_message`)
* **출력:** `generators` — `[{name, category, code, seeds, description}]`
* **왜 이 접근인가:**
    * LLM이 직접 100KB 입력을 출력하면 토큰 비용 폭발.
    * 스크립트 1개 × 시드 5개 = 5개의 대규모 입력이 무료로 생성.
    * 시드 고정 → 결정론적 재현 가능.
* **카테고리:** `RANDOM_SMALL`, `RANDOM_MEDIUM`, `MAX_STRESS`, `SPECIAL_STRUCTURE` 등
* **확장성:** 추후 각 카테고리별 전담 에이전트로 분리 가능.

### 📌 Node 5: [The Executor] - 3-Phase Runtime Verifier
* **환경:** Python `subprocess` + **Sandboxed Runner** (§4.5.1 참조). JDK / Python은 sandbox 이미지 또는 호스트에 설치.
* **핵심 역할:** 에이전트 개입 없이 코드를 격리 환경에서 물리적으로 3단계 검증.
* **입력:** `solution_code`, `sample_testcases`, `adversarial_inputs`, `generators`, `constraints_structured`
* **출력:** `execution_results`, `testcases`, `final_status`, `last_failed_node`, `feedback_message`
* **3-Phase 검증 로직:**

| Phase | 대상 | Oracle | 판정 기준 |
|---|---|---|---|
| **A: Sample Correctness** | Architect의 sample_testcases | Architect가 제공한 `expected_output` (또는 special_judge_code) | stdout == expected (special judge 시 checker 결과) |
| **B: Adversarial Small** | Auditor의 adversarial_inputs | 골든 솔루션 출력 자체 | status == OK (RTE/TLE 없음) + adversarial input이 constraints_structured에 부합 |
| **C: Generator Stress** | Generator 스크립트 × 시드별 실행 | 골든 솔루션 출력 자체 | status == OK + 정해 max-stress 실행시간 ≤ time_limit × 0.5 |

* **상세 로직:**
    1. `solution_code`를 sandbox 작업 디렉토리에 저장 및 컴파일 (실패 시 → Coder).
    2. 산출물 누락 체크 (samples 없음 → Architect, adversarial 없음 → Auditor, generators 없음 → Generator).
    3. **Phase A:** sample 입력을 stdin으로 주입(constraints_structured.time_limit_ms × 2 timeout), stdout과 expected_output 비교.
        * 휴리스틱 라우팅 (3-way):
            * **다수 통과 + 소수 실패 + 크래시 없음** → Architect (sample expected_output 오답 의심)
            * **전체 실패 + 컴파일 OK + 모든 sample에서 솔루션이 일관된 출력 생성** → **Architect** (sample 전체가 잘못됐을 가능성 — 신규 분기, REVIEW W3)
            * **전체 또는 다수 실패 + 출력 패턴이 일관되지 않거나 크래시 동반** → Coder (솔루션 버그)
        * `has_special_judge=true`일 경우 stdout 비교 대신 `special_judge_code` 실행 결과 사용.
    4. **Phase B:** adversarial 입력 syntactic validator 통과 후 실행 (`constraints_structured.variables` 범위 확인). validator 실패 → Auditor로 (input 자체가 잘못됨). 솔루션 RTE/TLE 없으면 솔루션 출력을 oracle로 testcase에 추가.
    5. **Phase C:** generator 스크립트를 시드별로 실행하여 stdin 생성 → 솔루션 실행. 스크립트 자체 실패 → Generator로, 솔루션 RTE/TLE → Coder로.
        * **추가 게이트:** max-stress 케이스에서 정해 wall_time이 `time_limit_ms × 0.5`를 넘으면 "정해가 느림" 피드백과 함께 Coder로 (성능 개선 요청).
    6. **병렬 실행 (P1):** Phase B/C는 case·seed 단위 embarrassingly parallel — `ThreadPoolExecutor`로 fan-out (subprocess는 GIL 영향 없음). 기본 4 worker, `--exec-workers`로 조정.
    7. **All Pass:** `final_status = "success"` → Difficulty Evaluator로 진행.
    8. **Termination:** 글로벌 `max_iter` 초과 → `max_iterations`. 노드별 `node_retry_budget` 소진 → `budget_exhausted`. `cost_usd` 합이 `max_cost_usd` 초과 → `cost_exceeded`. 어느 경우든 Halt → Human Review.

#### 4.5.1 Sandboxing & Resource Limits

LLM이 생성한 코드를 **호스트에서 직접 실행하지 않음**. 3-tier 격리 정책 (배포 환경에 따라 선택):

| Tier | 격리 수단 | 격리 범위 | 의존성 | 지원 OS |
|---|---|---|---|---|
| **T1 (권장 / Production / Cross-platform)** | Docker 컨테이너 (`--network=none --read-only --tmpfs /work --pids-limit --memory --cpus`) | 프로세스·네트워크·파일시스템 완전 격리 | Docker daemon (Docker Desktop on macOS/Windows) | Linux / macOS / Windows |
| **T2 (Linux dev)** | `nsjail` 또는 `firejail` / `bubblewrap` + cgroups v2 | 프로세스·네트워크·FS 격리 (이미지 빌드 불필요) | nsjail/firejail 바이너리 + Linux 커널 namespaces | **Linux 전용** |
| **T2.5 (macOS dev)** | `sandbox-exec` (Apple Sandbox profile, deprecated이지만 동작) + RLIMIT | 파일시스템·네트워크 정책 기반 격리 (프로세스 격리는 약함) | macOS 표준 (별도 설치 X) | **macOS 전용** |
| **T3 (최소 / 호환성)** | `resource.setrlimit()` only (`RLIMIT_AS`, `RLIMIT_CPU`, `RLIMIT_NOFILE`, `RLIMIT_NPROC`) + `subprocess` cwd 분리 | 프로세스 리소스만 통제 (네트워크·파일시스템 노출) | 표준 라이브러리 | Linux / macOS |

* **공통 강제 항목:**
    * **Memory cap**: `constraints_structured.memory_limit_mb` (기본 512MB) — `RLIMIT_AS` 또는 `--memory`.
    * **CPU time cap**: `constraints_structured.time_limit_ms × 2` — `RLIMIT_CPU` 또는 `--cpus` + wall-clock fallback.
    * **Output cap**: stdout 최대 5MB, stderr 최대 1MB (truncate).
    * **Process cap**: 자식 프로세스 ≤ 16 (`RLIMIT_NPROC` 또는 `--pids-limit`).
    * **Network**: 차단 (T1/T2/T2.5 강제, T3는 best-effort 경고).
    * **Filesystem**: workdir 외부 쓰기 차단 (T1 read-only + tmpfs, T2 nsjail bind, T2.5 sandbox-exec deny file-write*, T3 cwd만 분리하고 권한은 OS user에 의존).

* **OS별 자동 선택 (`--sandbox auto`):**

| OS | 우선순위 | 비고 |
|---|---|---|
| **Linux** | T1 (docker 가능) → T2 (nsjail/firejail) → T3 | T2가 가장 가벼움 |
| **macOS** | T1 (Docker Desktop 가능) → T2.5 (sandbox-exec) → T3 + 경고 | nsjail/firejail은 동작하지 않음 |
| **Windows** | T1 (Docker Desktop) → T3 + 경고 | T2/T2.5 모두 미지원 |

* **MVP 기본값 (Cross-platform):** `--sandbox auto`. **운영/CI는 `--sandbox docker` 강제 권장**.
* **macOS 개발 환경 주의사항:**
    * `nsjail`, `firejail`, `bubblewrap`은 **Linux 전용**이므로 macOS에서 동작하지 않는다.
    * Docker Desktop이 설치되어 있다면 T1을 우선 사용하라.
    * Docker가 없다면 T2.5(sandbox-exec)로 fallback. 단, Apple이 deprecated로 표시했으므로 미래 macOS 버전에서 작동 보장 없음.
    * Docker도 sandbox-exec도 사용 불가시 T3로 fallback하되 **`sandbox_isolation_pass`는 false로 기록**되며, `--strict-sandbox`가 켜져 있으면 즉시 abort.
* **검증 메트릭:** `sandbox_isolation_pass` — 의도된 격리 테스트(예: `socket.gethostbyname("google.com")` 시도, `/etc/passwd` 읽기 시도)가 차단되는지 자체 점검. T1/T2/T2.5만 통과 가능.

### 📌 Node 6: [The Evaluator] - Difficulty Assessor
* **사용 모델:** Claude Opus 4.7
* **핵심 역할:** Executor 검증을 통과한 완성된 문제에 대해 **알고리즘적 난이도를 사후 측정**.
* **입력:** `problem_description`, `constraints` + `constraints_structured`, `solution_code`, `execution_results`, `testcases`, **calibration anchor set** (백준 표준 난이도별 reference 샘플)
* **출력:** `difficulty_label`, `difficulty_reasoning`, `difficulty_factors`, `difficulty_calibration_anchors` (사용된 anchor 목록)
* **평가 기준 (difficulty_factors):**

| 요소 | 설명 | 예시 |
|---|---|---|
| `algorithm_complexity` | 핵심 알고리즘의 이론적 난이도 | "Dijkstra + Priority Queue → Gold 수준" |
| `implementation_difficulty` | 구현 복잡도 (자료구조, 예외처리 등) | "Segment Tree with lazy propagation → 높음" |
| `edge_case_density` | 엣지케이스의 밀도와 함정 수준 | "빈 그래프, 음수 가중치 등 고려 필요" |
| `constraint_tightness` | 제약조건의 타이트함 (최적해 강제 정도) | "N=200,000, 2초 → O(N log N) 강제" |
| `conceptual_leap` | 문제→알고리즘 연결의 직관성 | "그래프 모델링 필요 → 비자명" |

* **난이도 체계:** 백준 기준 (Bronze 5 ~ Ruby 1) 또는 Codeforces 레이팅 (800~3500) 중 택 1. MVP에서는 백준 체계 사용.
* **Calibration Anchor Set (분산 축소):**
    * 프롬프트에 anchored few-shot 샘플을 동봉 (Bronze 5 / Silver 3 / Gold 3 / Platinum 3 각 1~2문제, 짧은 description + 핵심 difficulty_factors).
    * 평가자가 anchor 대비 상대적 위치를 판단하여 절대 라벨을 부여 → run-to-run 분산 감소.
    * Anchor set은 `ipe/calibration/anchors.json`에서 로드 (확장 가능).
* **MVP 체크포인트:**
    * 단순 알고리즘 이름으로 난이도를 때려맞추는 것이 아니라, 실제 제약조건·구현 복잡도·엣지케이스까지 종합적으로 고려.
    * `difficulty_reasoning`에 판정 근거를 상세히 기술하여 Human Review 가능하게.
    * `difficulty_calibration_anchors`에 사용된 anchor 샘플 ID 목록을 기록 (재현 가능성).
* **확장성:** 추후 다수 평가 에이전트의 투표/앙상블 방식으로 정확도 향상 가능 (P2 — Future).

---

## 5. MVP 실행 사이클 (LangGraph Control Flow)

1. **[Start]** 사용자 입력 (`target_algorithm`, `target_language`, optional `--max-iter`/`--max-cost-usd`/`--sandbox`).
   * `run_id` 발급 + `node_retry_budget` 초기화 + checkpointer DB 생성 (`outputs/<run_id>/checkpoint.db`).
2. **[Architect]** 지문 생성 → **[Coder]** 정답 코드 작성 → **[Auditor]** 적대적 엣지케이스 생성 → **[Generator]** 시드 기반 스크립트 작성
   * **병렬화 (P1):** Auditor와 Generator는 둘 다 (problem + solution)에만 의존 → fan-out 후 join 가능.
3. **[Executor]** 3-Phase Sandboxed 검증 (Sample → Adversarial → Stress). Phase B/C는 case·seed 단위 fan-out 가능.
4. **[Condition Check]**
    * **All Pass:** **[Evaluator]** 난이도 사후 측정 → 로컬 파일(JSON/MD)로 최종 결과물 저장 및 종료 (MVP 성공).
    * **Fail (컴파일 에러/로직 에러/TLE/정해 성능 부족):** 피드백 + `iteration_history` 동봉 → **[Coder]**로 이동.
    * **Fail (지문 모순/Sample 오답):** 피드백과 함께 **[Architect]**로 이동하여 문제 자체 수정.
    * **Fail (엣지케이스 부족/constraints 위반/오류):** 피드백과 함께 **[Auditor]**로 이동.
    * **Fail (Generator 스크립트 오류):** 피드백과 함께 **[Generator]**로 이동.
    * **각 라우팅 시:** 해당 노드의 `node_retry_budget[node]`을 1 차감. **0 미만이 되면** `final_status="budget_exhausted"`로 즉시 halt.
5. **Termination 종류:**

| `final_status` | 트리거 | 후속 조치 |
|---|---|---|
| `success` | All Pass | Evaluator → save_result |
| `max_iterations` | 글로벌 `iteration_count >= max_iter` | Halt + Human Review |
| `budget_exhausted` | 어떤 노드의 retry budget이 0 미만 | Halt + 어느 노드가 막혔는지 보고 |
| `cost_exceeded` | `sum(llm_calls.cost_usd) > max_cost_usd` | Halt + 부분 산출물 저장 |

6. **Per-Node Retry Budget 기본값** (CLI/환경변수로 override 가능, REVIEW Q5 갱신):

| Node | 기본 budget | 이유 |
|---|---|---|
| architect | 2 | 지문이 본질적으로 잘못된 경우는 드묾 |
| coder | **4** | 가장 자주 수정 필요 (TLE/RTE/WA). 이전 3 → REVIEW Q5: TLE→fix→다른에러 핑퐁이 흔하므로 1회 증가. |
| auditor | 2 | <8 case self-loop 등 단순 보강 |
| generator | 2 | 스크립트 오류는 반복적이지 않음 |

* **합계 10**.
* **글로벌 `max_iter=7`** (이전 5 → REVIEW Q5 갱신: 노드 합 -3로 조정하여 노드별 budget이 글로벌에 의해 무력화되지 않도록).
* 글로벌은 안전망, 노드별이 정밀 제어. 둘 중 먼저 도달하는 쪽이 halt 트리거.
* `--max-iter <N>` / `--budget-coder <N>` CLI 플래그로 override.

---

## 6. 산출물 구조 (Polygon-Style)

```
outputs/<run_id>/
├─ problem.json        # DB 인서트 가능한 정형 데이터 (난이도 포함)
├─ problem.md          # 사람이 읽는 형태
├─ solution.py 또는 Solution.java
├─ generators/
│  ├─ gen_random_small.py
│  ├─ gen_random_medium.py
│  └─ gen_max_stress.py
├─ tests/
│  ├─ 01.in / 01.out
│  ├─ 02.in / 02.out
│  ├─ ...
│  ├─ NN.in / NN.out
│  └─ manifest.json    # 각 케이스의 메타 (kind, category, generator, seed, exec_time)
├─ llm_traces/         # 모든 LLM 호출의 raw 입출력 (재현/디버깅)
│  ├─ 0001_architect.json     # {seq, node, model, system, user, response, tokens, cost_usd, ts}
│  └─ ...
└─ checkpoint.db       # LangGraph SqliteSaver — resume 가능
```

`problem.json` 내 핵심 필드:
```json
{
  "meta": {
    "run_id": "8a4f...",
    "target_algorithm": "Dijkstra",
    "target_language": "java",
    "iteration_count": 2,
    "final_status": "success",
    "generated_at": "2026-05-07T17:53:00Z",
    "sandbox_tier": "T2",
    "sandbox_isolation_pass": true,
    "llm_call_summary": {
      "total_calls": 7,
      "total_input_tokens": 24500,
      "total_output_tokens": 8200,
      "total_cost_usd": 1.23,
      "by_node": { "architect": 1, "coder": 2, "auditor": 1, "generator": 1, "evaluator": 1, "executor": 0 }
    }
  },
  "constraints_structured": {
    "variables": [{"name": "N", "min": 1, "max": 100000, "type": "int"}],
    "time_limit_ms": 2000,
    "memory_limit_mb": 256,
    "raw": "1 ≤ N ≤ 100,000, 시간 2초, 메모리 256MB"
  },
  "difficulty": {
    "label": "Gold 3",
    "reasoning": "Dijkstra with priority queue is standard Gold-level...",
    "factors": {
      "algorithm_complexity": "Gold — Dijkstra + Priority Queue",
      "implementation_difficulty": "중간 — 인접 리스트 + PQ 구현",
      "edge_case_density": "높음 — 음수 가중치, 단절 그래프 등",
      "constraint_tightness": "O(N log N) 강제",
      "conceptual_leap": "낮음 — 직관적 그래프 모델링"
    },
    "calibration_anchors": ["bj_1753_silver3", "bj_1916_gold5", "bj_1753_gold4"]
  },
  "iteration_history": [
    {"iter_index": 1, "node": "coder", "action": "fix", "error_signature": "wa_phase_a_idx_2", "feedback": "..."},
    {"iter_index": 2, "node": "coder", "action": "fix", "error_signature": "tle_phase_c_seed_3", "feedback": "..."}
  ],
  "problem": { ... },
  "solution": { ... },
  "generators": [ ... ],
  "testcases_inline": [ ... ],
  "testcase_manifest": [ ... ],
  "execution_results": [ ... ],
  "llm_calls": [ ... ]
}
```

---

## 7. MVP 성공 기준 (Success Metrics)

### 7.1 기능 정상성
* 에이전트 간의 루프가 무한루프에 빠지지 않고 정상적으로 피드백을 주고받으며 코드를 수정하는가?
* 로컬 Python 런타임이 Java/Python 코드를 정상적으로 실행하고 stdout/stderr를 안정적으로 파싱해내는가?
* 최종 산출물(JSON)이 추가적인 가공 없이도 향후 백엔드(Spring) DB 스키마에 바로 인서트 될 수 있는 정형화된 구조를 가지는가?
* **Difficulty Evaluator가 문제의 실제 난이도를 합리적인 근거와 함께 산출하는가?**
* **난이도 판정이 알고리즘 이름에 대한 단순 매핑이 아닌, 제약조건·구현 복잡도·엣지케이스를 종합적으로 고려한 결과인가?**

### 7.2 보안·격리 (P0)
* `sandbox_isolation_pass=true` — 의도된 위반 시도(network 호출, workdir 외부 쓰기, fork bomb)가 모두 차단되는가?
* `RLIMIT` 또는 컨테이너 cap이 적용되어, 의도적으로 메모리·CPU·프로세스를 초과하는 솔루션이 호스트 영향 없이 안전히 실패하는가?

### 7.3 비용·재현성 (P1)
* `cost_per_problem` 평균 $1~$3 / 최대 $5 (`max_cost_usd` 가드 작동) — 실측 분포가 가드 안에 머무는가?
* `replay_reproducibility`: 동일 `run_id` + `llm_traces`로 `--replay` 모드 실행 시 최종 산출물이 비트단위 동일한가?
* `iteration_oscillation_rate`: `iteration_history`에서 동일 `error_signature`가 2회 이상 반복되는 비율 — 목표 <10%.

### 7.4 운영 메트릭 (P1)
* `success_rate_per_algo`: 알고리즘별 성공률 (목표 ≥70% with 5 iter budget).
* `p50/p95 iter_count`: 알고리즘 난이도와 상관관계 일치하는가?
* `phase_failure_distribution`: Phase A/B/C 중 어디서 가장 많이 실패하는가? (튜닝 신호)

---

## 8. MVP Scope 분류

각 개선 항목의 우선순위와 MVP 적용 범위:

| Priority | 항목 | MVP 적용 |
|---|---|---|
| **P0** | Sandbox (T2 기본, T1/T3 옵션) | ✅ 필수 |
| **P0** | Per-node retry budget + iteration_history | ✅ 필수 |
| **P0** | LangGraph SqliteSaver checkpointer | ✅ 필수 |
| **P1** | Auditor‖Generator 병렬 분기 | 🟡 옵션 (`--parallel-fanout`) |
| **P1** | Phase B/C ThreadPoolExecutor 병렬 | ✅ 필수 (4 worker 기본) |
| **P1** | `constraints_structured` (problem별 timeout/memlimit) | ✅ 필수 |
| **P1** | LLM call accounting + cost guard (`max_cost_usd`) | ✅ 필수 |
| **P1** | `llm_traces/` 저장 + `--replay` 모드 | ✅ 필수 |
| **P1** | Calibration anchors for Evaluator | ✅ 필수 |
| **P1** | 구조적 로깅 + (옵션) LangSmith/OTel hook | ✅ 필수 (로깅), 🟡 옵션 (export) |
| **P2** | Special judge 노드 | 🔵 Future |
| **P2** | Brute-force cross-check | 🔵 Future |
| **P2** | 중복/유사문제 detection (`outputs/index.jsonl`) | 🔵 Future |
| **P2** | Difficulty ensemble | 🔵 Future |
| **P2** | 새 언어 (C++, Rust 등) | 🔵 Future |

* ✅ = MVP 본문에 구현/명시
* 🟡 = MVP에 코드 hook은 두되 기본 OFF
* 🔵 = MVP 본문에서 제외, ARCHITECTURE.md §8 확장 포인트에만 언급