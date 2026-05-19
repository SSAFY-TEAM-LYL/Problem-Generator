# IPE 요구사항 정의서

> **프로젝트**: IPE (Infinite Problem Engine) — 알고리즘 문제 자동 생성 파이프라인
> **버전**: v0.2.0-rc (Sprint 3 진행 중, 2026-05-15 기준)
> **참조 문서**: [PROJECT_SPEC.md](PROJECT_SPEC.md) (기술 스펙) · [ARCHITECTURE.md](ARCHITECTURE.md) (모듈 설계) · [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) (12-phase 구현 일정)

---

## 1. 개요

### 1.1 시스템 목적
LLM(Claude)과 LangGraph를 이용해 외부 문제 소스에 의존하지 않고 알고리즘 문제(SWEA B형, 백준 골드 수준 포함)를 **자체 생산**하는 파이프라인. 문제 설계 → 정해 작성 → 적대적 엣지케이스 → 시드 기반 stress test → 난이도 사후 평가까지 자동화.

### 1.2 사용자
- **1차 사용자**: 알고리즘 강사 / 코딩 테스트 출제자 / 교육 콘텐츠 제작팀
- **2차 사용자**: 학습용 무한 문제 풀이 환경을 원하는 개발자 / 학생
- **운영자**: 본 시스템을 호스팅하고 모니터링하는 DevOps 엔지니어

### 1.3 시스템 범위
**범위 내(In Scope)**:
- 한 algorithm 키워드 → 한 검증된 문제 (problem.json + solution + testcases)
- 단일 사용자, 단일 실행 단위 (run_id 별 격리)
- Python / Java 솔루션 언어
- Sandboxed local execution (Docker / nsjail / sandbox-exec / RLIMIT)

**범위 외(Out of Scope)**:
- 웹 UI / 사용자 인증 / 다중 사용자 세션
- 자동 채점 시스템 통합 (출력만 호환 schema로 제공)
- 문제 데이터베이스 / 검색 인터페이스
- 다언어 문제 description 번역

---

## 2. 기능 요구사항 (Functional Requirements)

### FR-1: 문제 자동 생성 (Architect)

| 항목 | 내용 |
|---|---|
| ID | FR-1 |
| 설명 | 사용자가 `--algorithm <keyword>`로 알고리즘 키워드를 입력하면, Architect 노드가 storytelling을 입힌 문제 description + structured constraints를 생성한다. |
| 입력 | `target_algorithm: str` (예: "BFS shortest path") |
| 출력 | `problem_title`, `problem_description`, `constraints`, `constraints_structured`, `sample_testcases (3-5 cases)` |
| 검증 | (a) constraints_structured에 N/M/V 범위 변수 존재, (b) sample testcases가 description과 일관, (c) Phase A에서 sample 통과 가능한 정해 존재 |

### FR-2: 정해 작성 (Coder)

| 항목 | 내용 |
|---|---|
| ID | FR-2 |
| 설명 | Architect의 문제 description + constraints를 입력으로 받아 정해(golden solution)를 작성한다. 시간/메모리 제약 안에서 동작해야 한다. |
| 입력 | `problem_description`, `constraints`, `target_language` |
| 출력 | `solution_code: str` (펜스 코드 블록) |
| 부가 기능 (v0.2.0 Sprint 3) | (a) **LESSON 추출**(R13) — 매 cycle 응답 시작에 1줄 학습 누적, (b) **Brute solution 동시 작성**(R15) — Phase C cross-check 용, (c) **Best-of-N fanout**(R14) — `--coder-fanout N`으로 N candidate 생성 + Executor가 sample 검증으로 best 선택 |
| 특이 케이스 | 본질적으로 풀 수 없는 문제 → `IMPOSSIBLE: <reason>` 한 줄로 architect 재설계 요청 |

### FR-3: 적대적 입력 생성 (Auditor)

| 항목 | 내용 |
|---|---|
| ID | FR-3 |
| 설명 | 정해를 깰 만한 적대적 엣지케이스 N개를 생성한다 (경계값, 빈 입력, 동일 원소, 최대 N 등). 각 입력이 `constraints_structured`에 부합하는지 syntactic validator로 검증. |
| 입력 | `problem_description`, `constraints_structured`, `solution_code` |
| 출력 | `adversarial_inputs: list[dict]` (각 입력 + category + reason) |
| 라우팅 | validator 실패 다수 → 본인 노드 재실행 (constraints violator 제거), 실행 fail 다수 → Coder (솔루션 버그) |

### FR-4: 시드 기반 Stress Test (Generator)

| 항목 | 내용 |
|---|---|
| ID | FR-4 |
| 설명 | 시드 기반 deterministic generator script 3-5개를 작성 (Codeforces Polygon 패턴). 카테고리: RANDOM_SMALL / RANDOM_MEDIUM / MAX_STRESS / SPECIAL_STRUCTURE. |
| 입력 | `problem_description`, `constraints`, `solution_code` |
| 출력 | `generators: list[{name, category, description, code, seeds}]` |
| 검증 | 각 generator는 (`<seed>`) 인자만으로 deterministic stdin 생성. **출력 크기 cap 2MB** (R10, v0.2.0 Sprint 2). |

### FR-5: 3-Phase 결정론적 검증 (Executor)

| 항목 | 내용 |
|---|---|
| ID | FR-5 |
| 설명 | 솔루션 + 입력 조합을 sandbox에서 실행해 정확성/성능 검증. |
| 단계 | **Phase A** (sample exact match) → **Phase B** (adversarial input 후 솔루션 OK 시 testcase로 추가) → **Phase C** (generator × seed stress) |
| 부가 게이트 | (a) **정해 성능 게이트** (P6.4) — max-stress wall_time이 time_limit × 0.5 초과 시 "정해가 느림" 시그널, (b) **Brute cross-check** (R15) — Phase C 통과 후 small N (≤1KB) stress case에서 golden vs brute 출력 비교 |
| 라우팅 (Phase A 3-way) | (a) 다수 통과 + 소수 실패 + 크래시 없음 → architect (sample 의심), (b) 전체 실패 + 일관된 unique 출력 → architect, (c) 다수 실패 + 크래시 → coder |

### FR-6: 난이도 사후 평가 (Evaluator)

| 항목 | 내용 |
|---|---|
| ID | FR-6 |
| 설명 | 검증 완료된 문제에 calibration anchor와 함께 난이도 등급 부여 (실버/골드/플래티넘 등). 분산 ↓를 위해 anchor problem set과 함께 LLM에 입력. |
| 입력 | 검증된 problem + solution + testcases + calibration anchors |
| 출력 | `difficulty_label`, `difficulty_reasoning`, `difficulty_factors`, `difficulty_calibration_anchors` |

### FR-7: Sandboxed Local Execution

| 항목 | 내용 |
|---|---|
| ID | FR-7 |
| 설명 | LLM이 생성한 코드는 격리된 환경에서만 실행한다. 4-tier fallback. |
| Tier | T1 Docker (가장 강한 격리) → T2 nsjail (Linux) → T2.5 sandbox-exec (macOS) → T3 RLIMIT-only (가장 약함) |
| 자동 선택 | OS와 가용성에 따라 자동 picker가 결정. CLI `--sandbox docker/sandboxexec/rlimit`로 강제 가능 |
| 격리 검증 | `make selftest-all` — network blocked / FS write blocked / memory limited / CPU limited / fork limited 자동 점검 |

### FR-8: Resume & Replay

| 항목 | 내용 |
|---|---|
| ID | FR-8 |
| 설명 | (a) 크래시 시 LangGraph SqliteSaver checkpoint에서 재개, (b) 동일 run을 LLM 비용 0으로 재현. |
| Resume | `ipe --resume <run_id>` → checkpoint.db에서 마지막 super-step 이후 재개 |
| Replay | `ipe --replay <run_id>` → llm_traces/*.json을 차례로 반환, 새 LLM call 없음 |
| 산출물 | `outputs/<run_id>/checkpoint.db` + `outputs/<run_id>/llm_traces/<seq>_<node>.json` |

### FR-9: 비용 가드 (Cost Guard)

| 항목 | 내용 |
|---|---|
| ID | FR-9 |
| 설명 | LLM 호출 cumulative cost가 `--max-cost-usd` 초과 시 즉시 halt. |
| 추적 | `LLMCallTracker`가 매 호출의 input/output tokens + 비용 누적, `state["llm_calls"]`에 저장 |
| 가격 | `ipe/observability.py:PRICING` (Anthropic list price 기준, Tier 할인 미반영 — upper bound) |
| Default | `--max-cost-usd 5.0` USD/run |

### FR-10: 관측성 (Observability)

| 항목 | 내용 |
|---|---|
| ID | FR-10 |
| 설명 | 모든 LLM 호출의 raw input/output을 디스크에 저장하여 디버깅/replay/감사 가능 |
| Trace 파일 | `outputs/<run_id>/llm_traces/<seq>_<node>.json` — `{seq, node, model, messages, response, usage, duration_ms, cost_usd}` |
| Metrics | `emit_metric(name, value, labels)` — 구조적 로그 (LangSmith / OTel 옵션 통합) |
| Replay | `ReplayTracker`가 LLM 대신 trace 파일 반환 — `ipe --replay <run_id>` |

### FR-11: 산출물 영속화 (Output Persistence)

| 항목 | 내용 |
|---|---|
| ID | FR-11 |
| 설명 | 검증된 문제는 DB-insertable schema (`problem.json`)와 사람이 읽는 markdown (`problem.md`)으로 저장. |
| 구조 | `outputs/<run_id>/{problem.json, problem.md, solution.{py,java}, generators/<name>.py, tests/NN.{in,out}, manifest.json, llm_traces/, checkpoint.db}` |
| 별칭 | `outputs/by-name/<timestamp>_<algo>` → `../<run_id>` symlink (사람이 찾기 쉬움) |

### FR-12: 반복 제어 (Bounded Iteration)

| 항목 | 내용 |
|---|---|
| ID | FR-12 |
| 설명 | 무한 루프 방지를 위한 3중 가드 |
| Global | `max_iter` (default 10) — 전체 cycle 한도 |
| Per-node retry budget | architect/coder/auditor/generator 각각 (SPEC §5 default 2/4/4/2) |
| Cost guard | `max_cost_usd` 합산 초과 시 halt |
| 종료 상태 | `success` / `max_iterations` / `budget_exhausted` / `cost_exceeded` 4종 |

### FR-13: Oscillation 감지 (W4)

| 항목 | 내용 |
|---|---|
| ID | FR-13 |
| 설명 | 같은 `error_signature`가 동일 노드에서 2회 이상 반복되면 prompt에 "DIFFERENT STRATEGY REQUIRED" 강한 경고 자동 삽입 |
| 구현 | `ipe/nodes/_history.py:build_history_section` — iteration_history 누적 후 signature counting |

### FR-14: 다언어 솔루션 (Multi-language Solution)

| 항목 | 내용 |
|---|---|
| ID | FR-14 |
| 설명 | `--language python` 또는 `--language java` 선택. 솔루션 컴파일/실행은 언어별 분기 |
| Python | `python3 solution.py` |
| Java | `javac Solution.java && java -cp . Solution` |
| 확장 | C++ / Go / Rust 등은 후속 (현재 미지원) |

---

## 3. 비기능 요구사항 (Non-Functional Requirements)

### NFR-1: 성능

| 항목 | 목표 | 측정 방법 |
|---|---|---|
| 단일 문제 생성 시간 | 평균 < 10분 (5 case 평균) | e2e Run wall_time |
| 단일 LLM 호출 latency | < 60s (Anthropic API timeout) | trace.duration_ms |
| Phase A sample 실행 | < 5s/sample (time_limit_ms default) | execution_results.elapsed_ms |
| Phase C stress 실행 | per-case < time_limit_ms × 0.5 (정해 성능 게이트) | max_stress_elapsed |
| 비용 | < $5 USD/문제 (평균, default cap) | cost_usd 합산 |

### NFR-2: 안정성 / 신뢰성

| 항목 | 목표 |
|---|---|
| **Sandbox 격리** | LLM 생성 코드가 host fs/network/RLIMIT를 침범 못 함. T1 Docker 기준 network 완전 차단 + FS readonly. |
| **체크포인트** | 크래시 시 마지막 super-step 이후 재개 가능. SqliteSaver `outputs/<run_id>/checkpoint.db`. |
| **Sandbox subprocess race** | Phase C 병렬 실행 시 `subprocess.Popen + preexec_fn(setrlimit)` race로 SIGXCPU 발생 — v0.2.0 R-sandbox에서 `PHASE_C_WORKERS=1`로 직렬화로 0% race. |
| **결과 재현성** | replay 모드에서 동일 run_id의 LLM 응답을 100% 재현 (LLM call 없이 trace 반환). |

### NFR-3: 보안

| 항목 | 요구 |
|---|---|
| API 키 | `.env` 파일 또는 OS env에서만 로드, 코드에 hardcoding 0건 |
| LLM 코드 격리 | 모든 실행 코드는 sandbox 안에서만 (host 직접 실행 차단) |
| 파일 시스템 | sandbox tier별 차등 — T1 Docker는 readonly bind mount, T3 RLIMIT는 OS user 권한만 |
| 네트워크 | T1/T2 격리 시 outbound 차단. T3는 OS 의존 (warning) |
| 시크릿 노출 | trace 파일에 API key 마스킹, problem.json에 user input 그대로 보존하되 환경 secrets 미포함 |

### NFR-4: 확장성

| 항목 | 요구 |
|---|---|
| 언어 추가 | 신규 언어는 `_write_source` / `_compile` / `_run_cmd` 3 함수 분기 추가만으로 지원 |
| LLM 모델 | `ipe/observability.py:PRICING` table에 모델 ID 추가 + `ipe/llm.py:get_chat` 호환. Opus/Sonnet/Haiku 무관 |
| Sandbox tier | 신규 격리 도구는 `SandboxedRunner` Protocol 구현 + `selector.py:pick_runner` 등록 |
| Sub-agent 분해 (Future) | Architect → (Algorithm_Agent + Implementation_Agent) 같은 fan-out 가능하도록 노드 인터페이스 열어둠 |

### NFR-5: 유지보수성

| 항목 | 기준 |
|---|---|
| 파일 크기 | 모듈별 ≤ 800 lines (실제 평균 ~400) |
| `main.py` | ≤ 180 lines (CLI entrypoint budget) |
| `executor.py` | ≤ 620 lines (3-Phase 오케스트레이션) |
| 타입 검사 | `mypy --strict` 0 errors |
| 린트 | `ruff check` 0 issues |
| 함수 길이 | < 50 lines (대부분), 100 lines hard cap |
| 의존성 | `requirements.txt` 명시, 미사용 dep 0건 |

### NFR-6: 테스트 / 품질

| 항목 | 목표 |
|---|---|
| **테스트 커버리지** | ≥ 80% (현재 93%) |
| **단위 테스트** | 모든 helper / parser / state transition |
| **통합 테스트** | LLM mock + 실제 sandbox로 노드 round-trip 검증 |
| **e2e 테스트** | 5 알고리즘 골든 set (Two Sum / BFS / Dijkstra / Segment Tree / LIS) — `pytest -m e2e` |
| **DoD (e2e)** | 5 case 중 4+ success (LLM 변동성 허용) — v0.2.0 진행 중 (Run 9 3/5 도달) |
| **CI** | GitHub Actions ubuntu-latest + macos-latest 매트릭스 |

### NFR-7: 비용 효율

| 항목 | 기준 |
|---|---|
| 비용 측정 정확도 | list price upper bound — Anthropic console 실제 청구 / 측정 ≈ 0.4 (Tier 할인 + cache 미반영) |
| 비용 가드 | 시스템 측정값 기준 `max_cost_usd` 초과 시 즉시 halt — 실제 청구액보다 보수적 cap |
| 모델 선택 | Coder/Architect는 Opus 4.7 (정확성), Evaluator는 Sonnet 4.6 가능 (future) |

### NFR-8: 관측성 / 디버깅

| 항목 | 요구 |
|---|---|
| 로그 | 구조적 로그 (`emit_metric` JSON line), level INFO/WARN/ERROR |
| Trace | 매 LLM 호출의 raw input/output 디스크 저장 (감사 + replay) |
| Metrics | LangSmith / OpenTelemetry hook 옵션 (`IPE_LANGSMITH=1` / `IPE_OTEL_ENDPOINT`) |
| Replay 모드 | LLM 비용 0으로 동일 run 재현 — 버그 디버깅 핵심 |
| 진단 도구 | `tests/integration/test_sandbox_stdin_large.py` — sandbox race 진단 정량 측정 |

### NFR-9: 운영성 (Operations)

| 항목 | 요구 |
|---|---|
| 설치 | `make install` → `pip install -e ".[dev]"` 한 줄 |
| 환경 변수 | `.env`로 격리 — `ANTHROPIC_API_KEY`, `IPE_LANGSMITH`, `IPE_OTEL_ENDPOINT` 등 |
| 사용 CLI | `ipe --algorithm "..."` 단일 명령 진입점 |
| Resume | `ipe --resume <run_id>` 한 줄로 재개 |
| Replay | `ipe --replay <run_id>` 한 줄로 재현 |
| Sandbox 진단 | `make selftest-all` |
| 산출물 | `outputs/<run_id>/` 자동 생성, 사람용 별칭 `outputs/by-name/...` 자동 link |

### NFR-10: Reproducibility (재현성)

| 항목 | 요구 |
|---|---|
| Generator | seed 기반 deterministic — 같은 seed → 같은 stdin |
| LLM | replay 모드에서 100% trace 기반 재현 |
| Sandbox | RLIMIT/timeout만 환경 의존, 실행 자체는 재현 가능 |
| Calibration | `difficulty_calibration_anchors` 저장으로 사후 검토 가능 |

---

## 4. 시스템 인터페이스

### 4.1 CLI 인터페이스

```bash
ipe --algorithm "Two Sum"           # 새 run
ipe --algorithm "BFS" --language java
ipe --algorithm "..." --max-iter 10 --max-cost-usd 5.0
ipe --algorithm "..." --coder-fanout 3        # R14 Best-of-N
ipe --resume <run_id>                          # 크래시 재개
ipe --replay <run_id>                          # LLM 비용 0 재현
ipe --sandbox rlimit --strict-sandbox         # 격리 강제
```

### 4.2 외부 시스템

| 시스템 | 인터페이스 | 목적 |
|---|---|---|
| **Anthropic API** | HTTPS REST (langchain-anthropic) | LLM 호출 |
| **Docker daemon** | local Unix socket | T1 sandbox |
| **nsjail** | subprocess | T2 sandbox (Linux) |
| **sandbox-exec** | subprocess | T2.5 sandbox (macOS) |
| **LangSmith** (옵션) | HTTPS | trace 외부 저장 |
| **OpenTelemetry** (옵션) | OTLP HTTP | distributed tracing |

### 4.3 산출물 schema

`outputs/<run_id>/problem.json` (DB-insertable):
```json
{
  "run_id": "...",
  "target_algorithm": "BFS shortest path",
  "problem_title": "...",
  "problem_description": "...",
  "constraints": "...",
  "constraints_structured": {...},
  "solution_code": "...",
  "testcases": [{"kind": "sample|adversarial|generated", "input": "...", "expected_output": "..."}],
  "difficulty_label": "gold",
  "final_status": "success",
  "iteration_history": [...]
}
```

---

## 5. 제약 사항 (Constraints)

### 5.1 기술 제약
- Python 3.11+
- macOS 또는 Linux (Windows 미지원 — sandbox tier 호환성)
- Anthropic API 액세스 필수 (replay 모드 제외)
- Docker는 옵션 (T1 사용 시)

### 5.2 비즈니스 제약
- LLM 비용 — 운영 시 사용량 모니터링 필수
- 생성 문제의 라이선스는 사용자 책임 (LLM 출력물에 대한 일반적 면책)

### 5.3 알려진 한계 (v0.2.1 시점)
- e2e success rate: 4/5 stable (v0.2.0 Run 11/12) + SegTree 0/4 → success 1회 직접 확인 (v0.2.1 Round 16). 결정적 fix 9종 적용했지만 LLM 응답 variance는 본질적 한계 — 단일 run 결과 보장 X (분포 개선).
- LLM 비결정성: 동일 알고리즘이 run마다 다른 fail mode 가능 — R14 Best-of-N + R-osc-break + R-coder-osc + R-phase-a-osc-break 등 결정적 차단 메커니즘으로 무한 반복은 boundary된 budget으로 종료 보장.
- Java integration test: Linux CI에서 RLIMIT_AS + JVM 불안정으로 skip (macOS만 검증).
- ~~ChatAnthropic hang resilience~~: ✅ v0.2.1 R12 — 529/429/timeout 자동 retry (2/4/8s exp backoff, max 3).
- Docker tier `-v` bind mount 사용 (v0.2.1 R-docker-mount) — host의 workdir이 컨테이너에 readwrite으로 보임. `--read-only` rootfs 유지로 격리 보장. macOS Docker Desktop은 default `/Users/` sharing path 사용 — 다른 경로 workdir 시 user가 Docker Desktop file sharing 설정 필요.
- BFS variance: Round 16~17 실측에서 다양한 fail mode 관찰 (sample-wrong oscillation / oracle slow / coder Traceback). LLM quality 한계로 deterministic fix만으로 5/5 보장 어려움. R5 brute oracle Phase B 확장이 근본 해결 후보 (v0.2.2 candidate).

---

## 6. 인수 기준 (Acceptance Criteria)

### 6.1 코어 인프라 (v0.1.0~v0.1.1 완료)
- [x] 12-phase 구현 (P0~P12) 모두 DoD 통과
- [x] tests 240+ passed, coverage 93%
- [x] ruff 0 / mypy --strict 0
- [x] 5-Phase 검증 (A/B/C + brute cross-check) 작동
- [x] Resume / Replay 검증
- [x] 4-tier sandbox + isolation self-test

### 6.2 LLM Quality (v0.2.0 진행 중)
- [x] R-sandbox fix (subprocess race 회피) — Run 9 3/5 도달
- [x] R1 detailed feedback / R10 generator size cap / R11 IO 강화 / R13 LESSON / R15 brute oracle
- [x] R14 Best-of-N (opt-in 구조 + best 선택)
- [ ] **DoD: 5/5 중 4+ success** (Run 10 측정 예정)

### 6.3 문서 / 운영
- [x] docs/dev/PROJECT_SPEC.md / ARCHITECTURE.md / IMPLEMENTATION_ROADMAP.md 완비
- [x] RCA / playbook (`docs/improvements/`)
- [x] CI GitHub Actions ubuntu + macOS 매트릭스 통과
- [x] README badge / status 최신화

---

## 7. 후속 (Future Scope)

| 항목 | 우선순위 | 비고 |
|---|---|---|
| Sub-agent 분해 (Algorithm + Implementation) | P2 | 노드 인터페이스 이미 열어둠 |
| 중복 문제 검출 (`outputs/index.jsonl` + embedding) | P2 | SPEC §2 명시 |
| 특수 채점기 (special judge) | P2 | SPEC §8 |
| 난이도 ensemble (다수 평가자) | P2 | SPEC §4.6 |
| 운영 hang resilience (R12) | P1 | ChatAnthropic timeout + retry |
| ulimit wrapper로 Phase C 병렬화 복귀 (R-sandbox v2) | P3 | 성능 회복 |
| 추가 언어 (C++ / Go / Rust) | P2 | `_write_source` 분기 추가만 |

---

## 부록 A — 용어 정의

| 용어 | 정의 |
|---|---|
| **run** | 한 algorithm 키워드 → 한 문제 생성의 단위. `run_id`로 식별. |
| **Phase A/B/C** | Executor의 3-Phase 검증 (sample / adversarial / stress). |
| **golden solution** | Coder가 작성한 정해. 빠른 알고리즘 + 시간/메모리 제약 통과. |
| **brute solution** | Coder가 동시 작성하는 naive 솔루션 (O(N²) 등). small N cross-check 용. |
| **adversarial input** | Auditor가 만든 엣지케이스 (경계값, 최악 패턴 등). |
| **stress test** | Generator가 시드로 만든 large N 입력. |
| **error signature** | iteration_history에서 같은 실패 패턴 식별용 해시. |
| **oscillation (W4)** | 같은 error signature가 동일 노드에서 반복되는 현상. |
| **calibration anchor** | 난이도 평가 분산 감소용 reference problem set. |

---

## 부록 B — 변경 이력 / 참조

- 구체 변경 이력: [CHANGES.md](CHANGES.md)
- RCA (v0.1.1 + Sprint 3): [`docs/improvements/2026-05-10_root-cause-analysis.md`](docs/improvements/2026-05-10_root-cause-analysis.md) · [`docs/improvements/2026-05-14_sandbox-infra-rca.md`](docs/improvements/2026-05-14_sandbox-infra-rca.md)
- Quality troubleshooting playbook: [`docs/improvements/2026-05-14_quality-troubleshooting.md`](docs/improvements/2026-05-14_quality-troubleshooting.md)
- 본 문서 작성 시점: 2026-05-15, main HEAD `97fc11b`, e2e Run 9 3/5 success
