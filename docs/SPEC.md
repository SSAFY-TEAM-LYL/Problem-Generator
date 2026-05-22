# IPE 시스템 명세서 (SPEC)

**프로젝트**: IPE — Infinite Problem Engine
**상태**: v0.3.0-rc1 (release tag 보류, baseline measurement 기반 판정 진행 중)
**최종 업데이트**: 2026-05-21
**SSOT**: 본 문서 + [PRINCIPLES.md](PRINCIPLES.md) + [ARCHITECTURE.md](ARCHITECTURE.md)
**구버전 통합**: REQUIREMENTS.md (v0.2.0-rc) + TECH_STACK.md (v0.2.0-rc) + docs/dev/PROJECT_SPEC.md 가 본 문서로 통합됨.

---

## 1. 시스템 개요

### 1.1 목적

LLM (Claude) + LangGraph 를 이용해 외부 문제 소스에 의존하지 않고 **검증된**
알고리즘 문제 (SWEA B형, 백준 골드 수준 포함) 를 자체 생성 + **사람 review 후
catalog 에 promote** 하는 파이프라인.

### 1.2 제품 positioning (2026-05-21 baseline measurement 후 재정의)

IPE 의 가치는 *generation quality* 가 아니라 **verification + catalog +
observability platform** 이다 (`docs/STRATEGIC_REVIEW_2026-05-21.md` §5).
N=3 baseline 측정 결과 단일 LLM call 대비 run-level success 우위 X
(`docs/baseline/v0.3.0-rc1-N3.md`):

- IPE run-level: 20% (3/15)
- baseline run-level: 27% (4/15)
- IPE sample-level: 87.7% — baseline 대비 **+9pp 우위** (검증 layer 효과)

따라서 IPE 의 hook:
- 4-tier sandbox 격리로 LLM 코드 host 격리
- 모든 LLM call replay 가능 (cost 0 reproduction)
- Catalog 에 promote 된 문제는 사람 review 통과 상태
- Phase B/C adversarial + stress generation
- single LLM 대비 sample-level pass +9pp

### 1.3 사용자

- **1차 사용자**: 알고리즘 강사 / 코딩 테스트 출제자 / 교육 콘텐츠 제작팀
- **2차 사용자**: 학습용 무한 문제 풀이 환경을 원하는 개발자 / 학생
- **운영자**: 본 시스템을 호스팅하고 모니터링하는 DevOps 엔지니어

### 1.4 시스템 범위

**범위 내 (In Scope)**:
- 한 algorithm 키워드 → 한 검증된 문제 (problem.json + solution + testcases)
- 단일 사용자, 단일 실행 단위 (run_id 별 격리)
- Python / Java 솔루션 언어
- Sandboxed local execution (Docker / nsjail / sandbox-exec / RLIMIT)
- Catalog 영속화 + 사람 review CLI (`docs/catalog/SCHEMA.md`)

**범위 외 (Out of Scope)**:
- 웹 UI / 사용자 인증 / 다중 사용자 세션
- 자동 채점 시스템 통합 (출력만 호환 schema 로 제공)
- 문제 데이터베이스 / 검색 인터페이스
- 다언어 문제 description 번역

---

## 2. 기능 요구사항 (Functional Requirements)

### FR-1: 문제 자동 생성 (Architect)

| 항목 | 내용 |
|---|---|
| 입력 | `target_algorithm: str` (예: "BFS shortest path") |
| 출력 | `problem_title`, `problem_description`, `constraints`, `constraints_structured`, `sample_testcases (3-5 cases)` |
| v0.3.0 M3 | Opus + Sonnet 순차 dual-call + structural consensus voting (단, A/B 측정 결과 net effect 0 — rollback 검토 중. `docs/baseline/m3-rollback-ab.md`) |
| 검증 | constraints_structured 형식 강제, sample testcases ≥ 3 |

### FR-1.5: Algorithm Designer (M1, v0.3.0)

| 항목 | 내용 |
|---|---|
| 입력 | Architect 출력 |
| 출력 | `algorithm_design: {name, pseudocode, complexity_target, edge_cases}` |
| 모델 | Sonnet 4.6 |
| 목적 | Coder 분해 — algorithm 선택 책임을 분리 |

### FR-2: 정해 작성 (Coder)

| 항목 | 내용 |
|---|---|
| 입력 | problem_description, constraints, target_language, algorithm_design (M1 산출) |
| 출력 | `solution_code` + `brute_solution_code` (R15) + `lessons_learned` (R13) |
| 부가 | `--coder-fanout N` (R14 Best-of-N), IMPOSSIBLE 선언 (impossible 문제) |

### FR-2.5: Adversarial Review (M4, v0.3.0)

| 항목 | 내용 |
|---|---|
| 입력 | solution_code + problem + samples + algorithm_design |
| 출력 | `review_status: "approved"|"rejected"`, `review_reasoning`, `review_weaknesses` |
| 라우팅 | approve → executor, reject → coder retry (weaknesses 동봉) |
| 모델 | Opus 4.7 |

### FR-3: 적대적 입력 생성 (Auditor)

5-N 적대적 엣지케이스 생성 + syntactic validator 로 constraints 부합 검증.

### FR-4: 시드 기반 Stress Test (Generator)

시드 기반 deterministic generator script 3-5개 (RANDOM_SMALL / RANDOM_MEDIUM /
MAX_STRESS / SPECIAL_STRUCTURE). 출력 크기 cap 2MB (R10).

### FR-5: 3-Phase 결정론적 검증 (Executor)

- **Phase A**: sample exact match + R5 brute oracle cross-check
- **Phase B**: adversarial input 검증 후 testcase 채택
- **Phase C**: generator × seed stress + 정해 성능 게이트 (wall_time ≤ time_limit × 0.5)
- Phase A 3-way 라우팅 (다수 통과 / 전체 unique fail / 다수 fail+crash)

### FR-6: 난이도 사후 평가 (Evaluator)

검증 완료된 문제에 calibration anchor 기반 난이도 등급 부여
(Bronze/Silver/Gold/Platinum).

### FR-7: Sandboxed Local Execution

4-tier fallback:
- T1 Docker (`--network=none --read-only` + `-v {cwd}:{cwd}:rw` bind mount)
- T2 nsjail (Linux)
- T2.5 sandbox-exec (macOS)
- T3 RLIMIT-only

`make selftest-all` 격리 자가진단 — network / FS / memory / CPU / fork.

### FR-8: Resume & Replay

- `ipe --resume <run_id>` — LangGraph SqliteSaver checkpoint 에서 재개
- `ipe --replay <run_id>` — llm_traces 차례로 반환, 새 LLM call 없음 (cost 0)

### FR-9: 비용 가드 (Cost Guard)

`--max-cost-usd` 초과 시 즉시 halt. `LLMCallTracker` 누적 + `state["llm_calls"]`
저장. PRICING (list price upper bound, Tier 할인 미반영).

### FR-10: 관측성 (Observability)

- LLM traces: `outputs/<run_id>/llm_traces/<seq>_<node>.json`
- `emit_metric(name, value, labels)` + LangSmith / OTel hook
- Replay mode 로 LLM 비용 0 디버깅

### FR-11: 산출물 영속화

`outputs/<run_id>/{problem.json, problem.md, solution.*, generators/, tests/,
manifest.json, llm_traces/, checkpoint.db}` + `outputs/by-name/<timestamp>_<algo>`
symlink.

### FR-12: Catalog 영속화 (v0.3.0 신규)

`--promote-to-catalog` flag 로 success run 만 `outputs/catalog/problems.jsonl`
에 등록 + symlink farm. 사람 review CLI: `python -m ipe.catalog {list, show,
approve, reject, promote}`. 자세한 schema 는 [`catalog/SCHEMA.md`](catalog/SCHEMA.md).

### FR-13: 반복 제어 + Oscillation 감지

- Global `max_iter` + per-node retry budget + cost guard
- `_history.py` 가 같은 error_signature 반복 시 prompt 에 "DIFFERENT STRATEGY"
  경고 자동 삽입
- 결정적 차단 메커니즘 (R-osc-break, R-coder-osc, R-phase-a-osc-break, R5 brute
  oracle 등) — 자세한 내용 [`improvements/oscillation.md`](improvements/oscillation.md)

### FR-14: 다언어 솔루션

- `--language python` (`python3 solution.py`) 또는 `--language java`
  (`javac Solution.java && java -cp . Solution`)
- 확장: C++ / Go / Rust 후속

### FR-15: Pre-Hook 인프라 (M2, v0.3.0)

`ipe/hooks.py` — registry + register_pre_hook 데코레이터 + wrap_with_pre_hooks.
LLM call 전 invalid state reject. 3 builtin:
- `check_problem_complete` (coder 진입 전)
- `check_solution_code_present` (executor 진입 전)
- `check_solution_imports` (stdlib 외 import reject)

### FR-16: Single LLM Baseline (v0.3.0 신규)

PRINCIPLES.md §3 — 매 release 마다 `python -m ipe.baseline batch` 로 단일 LLM
call 측정. `docs/baseline/<version>.md` 에 보관.

---

## 3. 비기능 요구사항 (Non-Functional Requirements)

### NFR-1: 성능

| 항목 | 목표 |
|---|---|
| 단일 문제 생성 시간 | 평균 < 10분 |
| 단일 LLM 호출 latency | < 60s (Anthropic API timeout) |
| Phase A sample 실행 | < time_limit_ms |
| Phase C stress per-case | < time_limit_ms × 0.5 (정해 성능 게이트) |
| 비용 | < $5 USD/run (default `--max-cost-usd 5.0`) |

### NFR-2: 안정성 / 신뢰성

| 항목 | 요구 |
|---|---|
| Sandbox 격리 | T1 Docker 기준 network 차단 + FS readonly. `make selftest-all` 통과 |
| 체크포인트 | 크래시 시 마지막 super-step 이후 재개. SqliteSaver |
| Subprocess race | `PHASE_C_WORKERS=1` 직렬화로 SIGXCPU 0% (R-sandbox) |
| 결과 재현성 | replay 모드 100% LLM call trace 기반 재현 |
| Anthropic 일시 장애 | 529/429/timeout 자동 retry (R12) — exponential backoff 2/4/8s, max 3 |

### NFR-3: 보안

| 항목 | 요구 |
|---|---|
| API 키 | `.env` 또는 OS env 만 — hardcoding 0 |
| LLM 코드 격리 | sandbox 안에서만 실행 (host 직접 차단) |
| 파일 시스템 | T1 readonly bind mount, T3 RLIMIT user 권한 |
| 네트워크 | T1/T2 outbound 차단. T3 OS 의존 |
| 시크릿 노출 | trace 파일 API key 마스킹 |

### NFR-4: 확장성

- 언어 추가: `_write_source` / `_compile` / `_run_cmd` 3 함수 분기
- LLM 모델: `ipe/observability.py:PRICING` table + `get_chat` 호환
- Sandbox tier: `SandboxedRunner` Protocol 구현 + `selector.py:pick_runner` 등록
- Sub-agent 추가: 노드 인터페이스 열어둠 (M1/M3/M4 가 실제 사례)

### NFR-5: 유지보수성

| 항목 | 기준 |
|---|---|
| 파일 크기 | ≤ 800 lines (실제 평균 ~400) |
| `main.py` | ≤ 200 lines (CLI entrypoint) |
| 타입 검사 | `mypy --strict` 0 errors |
| 린트 | `ruff check` 0 issues |
| 함수 길이 | < 50 lines 권장, 100 lines hard cap |
| 의존성 | `requirements.txt` 명시, 미사용 0 |
| **Complexity budget** (PRINCIPLES.md 룰 4) | 노드 ≤ 8, safety ≤ 12 |

### NFR-6: 테스트 / 품질

| 항목 | 목표 / 현재 |
|---|---|
| 커버리지 | ≥ 80% / 현재 93% |
| 단위 테스트 | 모든 helper / parser / state transition |
| 통합 테스트 | LLM mock + 실제 sandbox round-trip |
| e2e 테스트 | 5 algorithm anchor (Two Sum / BFS / Dijkstra / LIS / Segment Tree) — `pytest -m e2e` |
| **DoD (v0.3.0)** | e2e ≥ 80% — **미달, 현재 20% (3/15)**. Release 보류 + multi-mechanism rollback 검토. |
| CI | GitHub Actions ubuntu + macOS 매트릭스 |

### NFR-7: 비용 효율

- 비용 측정: list price upper bound (실제 청구 / 측정 ≈ 0.4 — Tier 할인 + cache 미반영)
- 비용 가드: `max_cost_usd` 초과 시 즉시 halt
- 모델: Opus 4.7 (Architect/Coder/Auditor/Generator/Evaluator/Reviewer) + Sonnet 4.6 (Designer, Architect M3 dual-call 두 번째 모델)

### NFR-8: 관측성 / 디버깅

- 구조 로그: `emit_metric` JSON line, level INFO/WARN/ERROR
- Trace: 매 LLM 호출의 raw input/output 디스크 저장
- Metrics: LangSmith (`IPE_LANGSMITH=1`) / OTel (`IPE_OTEL_ENDPOINT`)
- Replay 모드: LLM 비용 0 으로 동일 run 재현
- 진단: `tests/integration/test_sandbox_stdin_large.py`

### NFR-9: 운영성 (Operations)

```bash
make install        # pip install -e ".[dev]"
make lint           # ruff check + mypy --strict
make test           # pytest with coverage
make ci             # lint + test
make selftest-all   # sandbox isolation 검증
make clean          # cache/build 정리

ipe --algorithm "..."                  # 새 run
ipe --resume <run_id>                  # 크래시 재개
ipe --replay <run_id>                  # LLM 비용 0 재현
ipe --sandbox docker --strict-sandbox  # 격리 강제
ipe --promote-to-catalog               # 성공 run 을 catalog 에 등록
python -m ipe.baseline batch           # 단일 LLM baseline 측정
python -m ipe.catalog list             # catalog 목록
```

### NFR-10: 재현성 (Reproducibility)

- Generator: seed 기반 deterministic
- LLM: replay 모드 100% trace 기반 재현
- Sandbox: RLIMIT/timeout 만 환경 의존
- Calibration: `difficulty_calibration_anchors` 저장

---

## 4. 기술 스택

### 4.1 언어 · 런타임

- **Python 3.11+** (TypedDict `total=False` + asyncio task group + match)
- **Java 17 (Temurin)** — 선택 (Java 솔루션 시)

### 4.2 LLM · AI 프레임워크

| 라이브러리 | 버전 | 역할 |
|---|---|---|
| langgraph | ≥0.2.0 | 노드 그래프 + checkpointer + conditional edges |
| langgraph-checkpoint-sqlite | ≥3.0.0 | SqliteSaver |
| langchain-anthropic | ≥0.2.0 | ChatAnthropic wrapper |
| anthropic | ≥0.40.0 | SDK |

### 4.3 모델 매핑 (`ipe/llm.py` + `ipe/observability.py:PRICING`)

| 모델 ID | 용도 | 단가 ($/1M tokens) |
|---|---|---|
| `claude-opus-4-7` | Architect / Coder / Auditor / Generator / Evaluator / Reviewer | input 15 / output 75 |
| `claude-sonnet-4-6` | Designer (M1) / Architect M3 두 번째 호출 / Consensus | input 3 / output 15 |
| `claude-haiku-4-5-20251001` | future 후보 | input 1 / output 5 |

### 4.4 상태 관리 + 영속화

- **상태 schema**: `TypedDict(total=False)` — `ProblemState` (30+ field). 자세한
  구조는 [ARCHITECTURE.md](ARCHITECTURE.md).
- **체크포인트**: SQLite (`outputs/<run_id>/checkpoint.db`)
- **산출물 schema**: JSON (`problem.json` DB-insertable + `manifest.json`)
- **catalog**: JSONL (`outputs/catalog/problems.jsonl` — 1 row / problem)
- **사람용 출력**: Markdown (`problem.md`)
- **테스트 케이스**: `tests/NN.{in,out}` + manifest (Polygon-style)

### 4.5 실행 격리 (Sandbox 4-Tier)

| Tier | 도구 | 환경 | 강점 |
|---|---|---|---|
| T1 | Docker | 모든 OS (daemon 필요) | network 차단 + read-only rootfs + bind mount |
| T2 | nsjail | Linux only | namespace + seccomp + cgroup |
| T2.5 | sandbox-exec | macOS only | Apple Seatbelt |
| T3 | POSIX RLIMIT | 모든 OS | 마지막 fallback |

자동 선택: `ipe/sandbox/selector.py`. CLI `--sandbox`로 강제 가능.

### 4.6 테스트 · 품질

| 도구 | 버전 | 역할 |
|---|---|---|
| pytest | ≥8.0.0 | 러너 + marker (`slow`, `e2e`) |
| pytest-mock | ≥3.12.0 | LLM mock |
| pytest-cov | ≥4.1.0 | coverage + threshold |
| ruff | ≥0.5.0 | line-length=100, E/F/W/I/N/UP/B/C4/SIM |
| mypy | ≥1.10.0 | `--strict` + disallow_untyped_defs |

### 4.7 CI/CD

GitHub Actions, ubuntu-latest + macos-latest matrix, python 3.11. Step:
checkout → setup-python → setup-java 17 → install → ruff → mypy --strict →
pytest -m "not e2e" → coverage threshold. e2e 는 manual / nightly.

### 4.8 의존성 그래프

```
CLI (main.py)
  ↓
Orchestration (ipe/graph.py — LangGraph)
  ↓
Nodes (ipe/nodes/*)
  ↓                         ↓
Sandbox (ipe/sandbox/*)    LLM (ipe/llm.py — langchain-anthropic)
  ↓                         ↓
Docker/nsjail/seatbelt/RLIMIT    Anthropic API
```

Layer 분리:
- **CLI** (main.py): argparse + env + run/resume/replay 분기
- **Orchestration** (ipe/graph.py): node 등록 + decision routing
- **Nodes** (ipe/nodes/*.py): 비즈니스 로직
- **Infrastructure** (ipe/sandbox/, ipe/observability.py, ipe/llm.py): 외부 시스템 격리
- **Catalog** (ipe/catalog/*): success run 영속화 + 사람 review
- **Baseline** (ipe/baseline/*): 단일 LLM baseline 측정 (PRINCIPLES.md §3)

### 4.9 총 dependency 수

Core 6 + Dev 5 = **11** (의도적 최소화)

### 4.10 미사용 / 제외한 기술 (의도적)

| 후보 | 제외 사유 |
|---|---|
| OpenAI SDK | Anthropic 단일 provider (langchain-anthropic 으로 충분) |
| FastAPI / Flask | CLI tool 로 web layer 불필요 |
| Celery / Redis | 단일 사용자 / 단일 run — 큐 불필요 |
| PostgreSQL | JSON 파일 (DB-insertable schema 만) |
| Pydantic (v0 layer) | TypedDict + jsonschema 로 충분. v1 (`ipe/v1/`) 는 D안 H1 (structured artifacts) 검증 위해 Pydantic v2 도입 — PR-A1 (`CHANGES.md` §37) 참조 |
| Black + isort | ruff 통합 |
| pre-commit | Makefile + CI 로 enforce |
| Poetry / Hatch | setuptools + requirements.txt 로 충분 |

---

## 5. 인수 기준 (Acceptance Criteria)

### 5.1 코어 인프라 (v0.1.0~v0.1.1)

- [x] 12-phase 구현 (P0~P12) 모두 DoD 통과
- [x] 247+ tests passed, coverage 93%
- [x] ruff 0 / mypy --strict 0
- [x] 5-Phase 검증 (A/B/C + brute cross-check)
- [x] Resume / Replay 검증
- [x] 4-tier sandbox + isolation self-test

### 5.2 v0.2.0 (Sprint 1~3, 결정적 차단 시리즈)

- [x] R-sandbox / R10 / R11 / R12 / R13 / R14 / R15
- [x] R-osc-break / R-coder-osc / R-phase-a-osc-break / R5 brute oracle
- [x] Docker workdir + bind mount fix

### 5.3 v0.3.0-rc1 (Multi-mechanism RFC + Catalog + Measurement)

- [x] M1 AlgorithmDesigner / M2 Pre-Hook / M3 Multi-model consensus / M4 Adversarial review
- [x] Catalog 영속화 모듈 + CLI (`docs/catalog/SCHEMA.md`)
- [x] PRINCIPLES.md 5 운영 룰 SSOT
- [x] Single LLM baseline 측정 모듈 (`ipe/baseline/`)
- [x] N=3 측정 완료 (baseline + IPE)
- [ ] **DoD: e2e ≥ 80% — 미달 (현재 20% 3/15)** → tag 보류
- [ ] M3 rollback A/B 측정 후 multi-mechanism 일부 회수
- [x] **Strategic review 완료** (`docs/STRATEGIC_REVIEW_2026-05-21.md`)

---

## 6. 알려진 한계 / 변경 / 참조

### 6.1 알려진 한계 (v0.3.0-rc1 시점)

- **e2e success rate**: N=3 기준 **20% (3/15)**. LLM 비결정성 + multi-mechanism
  cost overhead 의 trade-off. 자세한 분석 [`baseline/v0.3.0-rc1-N3.md`](baseline/v0.3.0-rc1-N3.md)
  + [`baseline/analysis-N3-deeper.md`](baseline/analysis-N3-deeper.md).
- **M3 dual-call net effect 0**: A/B 측정 결과 quality 향상 X (Dijkstra baseline
  3/3 vs IPE 0/3). rollback 검토 PR 진행 중.
- **단일 LLM baseline 대비**: run-level -7pp 떨어짐 / sample-level +9pp 우위. IPE
  의 가치는 검증 layer 에 있음.
- **Java integration test**: Linux CI 에서 RLIMIT_AS + JVM 불안정으로 skip
  (macOS 만 검증).
- **Docker bind mount**: macOS Docker Desktop default `/Users/` sharing path.
  다른 경로 workdir 시 user 가 sharing 설정 필요.
- **stochasticity 본질적 한계**: LLM 응답 variance 가 큼. 동일 algorithm × 3
  run 에서 fail mode 가 매번 다름. architectural change (skill library, RAG)
  없이 천장 돌파 어려움.

### 6.2 v0.3.0 release 판정 진행 중

PRINCIPLES.md §3 결정 트리 적용:
- baseline ≈ IPE (|Δ run| < 20pp) → **IPE 는 검증 layer 만 정당화**
- 결론: v0.3.0 tag 보류 + multi-mechanism 일부 rollback

후속 PR 우선순위:
1. M3 dual-call rollback (가장 명백한 음효과)
2. coder budget tuning 재측정
3. skill library M5 (M3 자리)
4. release tag (DoD 재정의 또는 재측정 후)

### 6.3 변경 이력 + 참조

- 구체 변경 이력: [CHANGES.md](../CHANGES.md)
- 운영 정책 SSOT: [PRINCIPLES.md](PRINCIPLES.md)
- 시스템 구조: [ARCHITECTURE.md](ARCHITECTURE.md)
- v0.3.0 RFC: [`docs/rfc/v0.3.0_multi-mechanism.md`](rfc/v0.3.0_multi-mechanism.md)
- 측정 데이터: [`docs/baseline/`](baseline/)
- RCA (통합): [`docs/improvements/`](improvements/)
- Catalog schema: [`docs/catalog/SCHEMA.md`](catalog/SCHEMA.md)
- Strategic review: [`docs/STRATEGIC_REVIEW_2026-05-21.md`](STRATEGIC_REVIEW_2026-05-21.md)

---

## 부록 A — 용어 정의

| 용어 | 정의 |
|---|---|
| **run** | 한 algorithm 키워드 → 한 문제 생성의 단위. `run_id` 로 식별 |
| **Phase A/B/C** | Executor 의 3-Phase 검증 (sample / adversarial / stress) |
| **golden solution** | Coder 가 작성한 정해 |
| **brute solution** | Coder 가 동시 작성하는 naive 솔루션 (R15 cross-check) |
| **adversarial input** | Auditor 가 만든 엣지케이스 |
| **stress test** | Generator 가 시드로 만든 large N 입력 |
| **error signature** | iteration_history 의 같은 실패 패턴 식별용 해시 |
| **oscillation (W4)** | 같은 error signature 가 동일 노드에서 반복 |
| **calibration anchor** | 난이도 평가 분산 감소용 reference problem set |
| **catalog** | 사람 review 통과한 success run 의 영속화 layer |
| **baseline** | 단일 Opus call 로 problem+sample+solution 생성하는 비교 anchor |
| **complexity budget** | PRINCIPLES.md 룰 4: 노드 ≤ 8, safety ≤ 12 |
