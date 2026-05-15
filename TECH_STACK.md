# IPE 기술 스택

> **프로젝트**: IPE (Infinite Problem Engine)
> **목적**: MVP 구현 + 운영에 사용된 기술 스택 카탈로그
> **작성**: 2026-05-15, v0.2.0-rc 시점
> **참조**: [REQUIREMENTS.md](REQUIREMENTS.md) · [docs/dev/PROJECT_SPEC.md](docs/dev/PROJECT_SPEC.md) · [docs/dev/ARCHITECTURE.md](docs/dev/ARCHITECTURE.md)

---

## 1. 언어 · 런타임

| 항목 | 버전 | 선택 이유 |
|---|---|---|
| **Python** | 3.11+ | TypedDict `total=False` + match statement + 향상된 error message. LangGraph 공식 권장 |
| **Java** (선택) | 17+ (CI: Temurin) | Java 솔루션 컴파일/실행 분기. 17은 LTS + sandbox 호환 |

**Python 3.11 강제 이유**:
- `typing.NotRequired` / `Self` 같은 modern annotation
- `asyncio` task group (LangGraph 내부 사용)
- 성능 (10-25% 빨라짐)
- mypy strict 모드 호환성

---

## 2. LLM · AI 프레임워크

| 라이브러리 | 버전 | 역할 |
|---|---|---|
| **langgraph** | ≥0.2.0 | 노드 그래프 오케스트레이션. Architect/Coder/Auditor/Generator/Executor/Evaluator 노드 + decision 노드 |
| **langgraph-checkpoint-sqlite** | ≥3.0.0 | SqliteSaver — 크래시 복구용 super-step 체크포인트 |
| **langchain-anthropic** | ≥0.2.0 | `ChatAnthropic` wrapper — Claude API 호출 |
| **anthropic** | ≥0.40.0 | Anthropic Python SDK (langchain-anthropic의 underlying) |

### 모델 선택 (`ipe/observability.py:PRICING`)

| 모델 ID | 용도 | 단가 ($/1M tokens) |
|---|---|---|
| `claude-opus-4-7` | Architect / Coder / Auditor / Generator / Evaluator (정확성 우선) | input 15 / output 75 |
| `claude-sonnet-4-6` | Sub-agent 분해 시 후보 (future) | input 3 / output 15 |
| `claude-haiku-4-5-20251001` | 경량 호출 후보 (future) | input 1 / output 5 |

**현재 운영**: Opus 4.7 단일 모델 (정확성 최우선).
**비용 측정**: list price upper bound — Anthropic Tier 할인 / cache는 미반영 (실제 청구액 / 측정 ≈ 0.4).

---

## 3. 상태 관리 · 데이터

| 항목 | 기술 | 목적 |
|---|---|---|
| **상태 schema** | `TypedDict (total=False)` | `ProblemState` — 노드 사이 흐르는 상태 dict. 점진 채움 |
| **체크포인트 저장소** | SQLite (langgraph) | `outputs/<run_id>/checkpoint.db` — 크래시 시 재개 |
| **산출물 schema** | JSON | `problem.json` (DB-insertable) + `manifest.json` (디렉토리 메타) |
| **검증** | jsonschema ≥4.20.0 | `constraints_structured` 등 LLM 출력 schema 검증 |
| **사람용 출력** | Markdown | `problem.md` (사람이 읽는 문제 설명) |
| **테스트 케이스** | `tests/NN.{in,out}` 파일 + manifest | Polygon-style 디렉토리 구조 |

### ProblemState 핵심 필드 (TypedDict)

```python
class ProblemState(TypedDict, total=False):
    run_id: str
    target_algorithm: str
    iteration_count: int
    max_iter: int
    node_retry_budget: NodeRetryBudget
    max_cost_usd: float | None
    # Architect / Coder / Auditor / Generator / Executor / Evaluator output...
    lessons_learned: list[str]        # R13
    brute_solution_code: str           # R15
    coder_fanout: int                  # R14
    candidate_solutions: list[dict]    # R14
    final_status: FinalStatus | None   # success / max_iterations / budget_exhausted / cost_exceeded
    iteration_history: list[IterationRecord]
    llm_calls: list[LLMCallRecord]
```

---

## 4. 실행 격리 · Sandboxing (4-Tier)

| Tier | 도구 | 환경 | 강점 |
|---|---|---|---|
| **T1** | **Docker** | 모든 OS (daemon 필요) | Network 차단 + FS readonly bind mount + cgroup |
| **T2** | **nsjail** | Linux only | namespace + seccomp + cgroup |
| **T2.5** | **sandbox-exec** | macOS only | Apple Seatbelt policy |
| **T3** | **POSIX RLIMIT** | 모든 OS | 마지막 fallback. RLIMIT_AS + RLIMIT_CPU + RLIMIT_NPROC |

### 자동 선택 (`ipe/sandbox/selector.py`)
- macOS: T2.5 (sandbox-exec) → T1 (Docker) → T3
- Linux: T1 (Docker) → T2 (nsjail) → T3
- 사용자: `--sandbox docker/sandboxexec/rlimit`로 강제 가능

### 격리 검증
```bash
make selftest-all  # 각 tier별 network/fs/memory/cpu/fork 격리 자동 점검
```

### 알려진 한계 (v0.2.0)
- **subprocess + preexec_fn race** (R-sandbox): `ThreadPoolExecutor(max_workers=4)` 병렬 시 RLIMIT_CPU race로 SIGXCPU(-24). **PHASE_C_WORKERS=1**로 직렬화 (Sprint 3, PR #38)
- **Linux JVM**: RLIMIT_AS + JVM 상호작용 불안정 — Java integration test는 Linux CI skip (macOS만 검증)

---

## 5. 테스트 · 품질

### 5.1 테스트 프레임워크

| 라이브러리 | 버전 | 역할 |
|---|---|---|
| **pytest** | ≥8.0.0 | 테스트 러너. markers `slow` / `e2e` 등록 |
| **pytest-mock** | ≥3.12.0 | LLM mock (`monkeypatch("ipe.nodes.coder.get_chat", ...)`) |
| **pytest-cov** | ≥4.1.0 | coverage 측정 + threshold (`--cov-fail-under=80`) |

### 5.2 코드 품질

| 도구 | 버전 | 설정 |
|---|---|---|
| **ruff** | ≥0.5.0 | line-length=100, select E/F/W/I/N/UP/B/C4/SIM (`pyproject.toml`) |
| **mypy** | ≥1.10.0 | `--strict` + disallow_untyped_defs + warn_unused_configs |

### 5.3 테스트 구조

```
tests/
├── test_*.py                    # 단위 테스트 (parser, state, helpers)
├── integration/                 # 통합 테스트 (LLM mock + 실제 sandbox)
│   ├── test_minimal_circuit.py
│   ├── test_phase_b.py / test_phase_c.py
│   ├── test_executor_java.py    # Linux skip
│   ├── test_sandbox_stdin_large.py  # R-sandbox 진단
│   └── test_coder_fanout.py     # R14
├── sandbox/                     # Sandbox isolation self-test
└── e2e/test_smoke.py            # 5 알고리즘 golden set (실제 LLM, manual)
```

### 5.4 현재 통계 (main `0003332`)
- **247 tests passed** + 3 skipped (CI 기본)
- **Coverage: 93%** (≥80% 기준 통과)
- ruff 0 / mypy --strict 0

---

## 6. CI/CD

| 항목 | 기술 | 설정 |
|---|---|---|
| **CI Provider** | GitHub Actions | `.github/workflows/ci.yml` |
| **Runner Matrix** | ubuntu-latest + macos-latest | python 3.11 |
| **Step 순서** | checkout → setup-python (cache pip) → setup-java 17 (Temurin) → install deps → ruff → mypy --strict → pytest -m "not e2e" → coverage threshold | |
| **e2e 처리** | manual / nightly (CI 기본 제외) | `ANTHROPIC_API_KEY` 비밀 필요 |
| **Branch protection** | main 직접 push 차단, PR 머지 필수 | (GitHub 설정) |

---

## 7. 관측성 · 로깅

| 항목 | 기술 | 목적 |
|---|---|---|
| **LLM trace** | 자체 구현 (`LLMCallTracker`) | 매 LLM 호출의 messages/response/usage/cost 디스크 저장 — `llm_traces/<seq>_<node>.json` |
| **구조 로그** | stdlib `logging` + JSON formatter | `emit_metric(name, value, labels)` |
| **Replay** | `ReplayTracker` | LLM 비용 0으로 동일 run 재현 (디버깅 + 감사) |
| **LangSmith** (옵션) | env `IPE_LANGSMITH=1` | langchain trace 외부 저장 |
| **OpenTelemetry** (옵션) | env `IPE_OTEL_ENDPOINT` | OTLP HTTP distributed tracing |

### Cost 측정
- `LLMCallTracker.invoke()`가 매 호출의 input/output tokens × PRICING table → cost_usd
- `state["llm_calls"]`에 cumulative 저장
- `max_cost_usd` 초과 시 즉시 halt → `final_status="cost_exceeded"`

---

## 8. 환경 / 비밀 관리

| 항목 | 기술 | 목적 |
|---|---|---|
| **환경 변수** | `.env` + python-dotenv ≥1.0.0 | API key / feature toggle 격리 |
| **필수 키** | `ANTHROPIC_API_KEY` | replay 모드 외 모든 실행 |
| **선택 키** | `IPE_LANGSMITH`, `IPE_OTEL_ENDPOINT`, `LANGCHAIN_API_KEY` | 운영 관측성 |
| **버전 관리** | `.env.example`만 commit, `.env`는 `.gitignore` | API key 노출 차단 |

---

## 9. 패키지 · 빌드 · 의존성 관리

| 항목 | 기술 |
|---|---|
| **Build backend** | `setuptools>=64 + wheel` (`pyproject.toml` build-system) |
| **Editable install** | `pip install -e ".[dev]"` |
| **Entrypoint** | `[project.scripts] ipe = "main:main"` (선택 — 현재 `python main.py` 사용) |
| **Lockfile** | 없음 (requirements.txt + pyproject.toml 양쪽 명시) |
| **Virtual env** | `.venv` (python -m venv) |
| **편의 명령** | `Makefile` (install / lint / test / ci / clean / selftest-all 등) |

### Makefile 주요 target
```bash
make install        # pip install -e ".[dev]"
make lint           # ruff check + mypy --strict
make test           # pytest with coverage
make ci             # lint + test
make selftest-all   # sandbox isolation 검증
make clean          # cache/build 정리
```

---

## 10. 개발 도구 · 워크플로

| 항목 | 도구 |
|---|---|
| **VCS** | Git + GitHub (LsMin124/IPE + dual-push SSAFY-TEAM-LYL/Problem-Generator) |
| **Branch 전략** | feature branch + PR → main fast-forward 머지 |
| **Commit convention** | conventional (`feat:` / `fix:` / `docs:` / `chore:` / `test:` 등) |
| **PR template** | Summary + Test plan + 검증 결과 |
| **Auto-attribution** | 비활성 (`~/.claude/settings.json` 설정) |

---

## 11. 운영 시 의존 외부 시스템

| 시스템 | 인터페이스 | 필요성 | 비고 |
|---|---|---|---|
| **Anthropic API** | HTTPS REST | 필수 | replay 모드 제외 |
| **Docker daemon** | local Unix socket | 옵션 | T1 sandbox 사용 시 |
| **nsjail** | subprocess | 옵션 | T2 (Linux) |
| **sandbox-exec** | subprocess | 옵션 | T2.5 (macOS) — 기본 OS에 포함 |
| **Java 17 (Temurin)** | local binary | 옵션 | 솔루션 언어 `--language java` 시 |

### 외부 시스템 부재 시 동작
- Docker 없음 → T2.5 또는 T3 fallback (자동)
- nsjail 없음 → T1 또는 T3 fallback (Linux)
- Java 없음 → Python만 가능
- Anthropic API 차단 → replay 모드만 동작

---

## 12. 보안 / 컴플라이언스 고려사항

| 항목 | 조치 |
|---|---|
| **API key 노출** | `.env` 격리 + git ignore + trace 파일에 마스킹 |
| **LLM 코드 실행** | 모든 LLM 출력 코드는 sandbox 안에서만 실행 (host 직접 실행 차단) |
| **Network egress** | T1 Docker 기준 차단. T2/T2.5도 차단. T3는 OS user 권한만 — 운영 시 T1 권장 |
| **File system 쓰기** | T1 readonly bind mount, T3는 tmp_path scope |
| **CSP / 인증** | 본 시스템은 CLI tool로 web 컨텍스트 없음 — 향후 API화 시 필요 |

---

## 13. 운영 / 디버깅 도구

| 도구 | 사용처 |
|---|---|
| `ipe --resume <run_id>` | 크래시 시 마지막 super-step에서 재개 |
| `ipe --replay <run_id>` | LLM 비용 0으로 동일 run 재현 (버그 진단 + 감사) |
| `make selftest-all` | sandbox tier별 isolation 검증 |
| `outputs/<run_id>/llm_traces/` | LLM 응답 디버깅 |
| `outputs/<run_id>/problem.md` | 사람이 읽는 결과 검토 |
| `tests/integration/test_sandbox_stdin_large.py` | sandbox race 진단 (R-sandbox 같은 인프라 이슈 측정) |

---

## 14. 미사용 / 제외한 기술 (의도적 결정)

| 후보 | 제외 사유 |
|---|---|
| **OpenAI SDK** | Anthropic 단일 provider (langchain-anthropic으로 충분, 모델 교체 시 wrapper만 변경) |
| **FastAPI / Flask** | CLI tool로 web layer 불필요 (향후 API화 시 도입) |
| **Celery / Redis** | 단일 사용자 / 단일 run 시점 — 큐 불필요 |
| **PostgreSQL** | 출력이 JSON 파일 (DB-insertable schema만 보장). 추후 DB layer는 별도 |
| **Pydantic** | TypedDict로 schema 충분 (jsonschema로 validate). pydantic은 dependency 비용 큼 |
| **Black + isort** | ruff로 통합 (isort 통합 + format 통합 — single tool 정책) |
| **pre-commit** | Makefile + CI로 enforce — pre-commit hook은 사용자 선택 |
| **Poetry / Hatch** | setuptools + requirements.txt로 충분. lockfile 없이 `>=` range 정책 |

---

## 15. 의존성 그래프 (간략)

```
[CLI main.py]
  ↓
[ipe.graph (langgraph)]
  ↓ (state 흐름)
[ipe.nodes.*]  ───────  [ipe.llm (langchain-anthropic)]
  ↓                          ↓
[ipe.sandbox.*]              [Anthropic API]
  ↓
[Docker / nsjail / sandbox-exec / RLIMIT]
  ↓
[Python subprocess + 솔루션 실행]
```

### Layer 분리
- **CLI** (main.py) — argparse + 환경 변수 + run/resume/replay 분기
- **Orchestration** (`ipe/graph.py`) — LangGraph node 등록 + decision routing
- **Nodes** (`ipe/nodes/*.py`) — 비즈니스 로직 (Architect/Coder/등)
- **Infrastructure** (`ipe/sandbox/*.py`, `ipe/observability.py`, `ipe/llm.py`) — 외부 시스템 격리

---

## 16. v0.2.0 시점 기술 결정 추적

| Sprint | 기술적 결정 | PR |
|---|---|---|
| Sprint 1 | Coder feedback 구체화 (R1) + Auditor budget 4 (R4) + PRICING 주석 (R6) | #29 |
| Sprint 1.5 | Coder system prompt buffered-IO 강제 (R11) | #30 |
| max_iter | e2e baseline 8→10 (cycle 여유) | #31 |
| Sprint 2 | Generator input cap 5MB→2MB (R10) | #32 |
| CI hotfix | Linux RLIMIT_AS + JVM 불안정 → Java test skip | #35 |
| Sprint 3 R13 | Coder LESSON 추출 + history 누적 (Reflexion) | #34 |
| Sprint 3 R15 | Coder brute solution + Phase C cross-check | #36 |
| **R-sandbox** | **`PHASE_C_WORKERS 4→1`** (subprocess race 회피) | **#38** |
| Sprint 3 R14 PR 1 | Coder fanout opt-in 구조 | #40 |
| Sprint 3 R14 PR 2 | Executor best 선택 (sample 검증) | #41 |

---

## 17. 후속 기술 검토 (Future)

| 기술 | 도입 시점 | 검토 사유 |
|---|---|---|
| **ulimit wrapper** (bash) | R-sandbox v2 | `PHASE_C_WORKERS=4` 복귀 — preexec_fn race 회피 |
| **httpx timeout + retry** | R12 | ChatAnthropic hang resilience |
| **FastAPI** | API화 시점 | 다중 사용자 / web UI 필요 시 |
| **PostgreSQL + pgvector** | 중복 검출 / embedding | SPEC §2 명시 (outputs/index.jsonl) |
| **Sub-agent (Algorithm / Implementation)** | 정확성 ↑ 필요 시 | 노드 인터페이스 이미 열어둠 |
| **Multi-model ensemble** | 분산 ↓ 필요 시 | difficulty evaluator 후보 |
| **Distributed sandbox** | scale 필요 시 | Kubernetes job + Firecracker 등 |

---

## 부록 — 한눈에 보는 dependency 매트릭스

| 카테고리 | 패키지 | 버전 | 라이선스 |
|---|---|---|---|
| Core | langgraph | ≥0.2.0 | MIT |
| Core | langgraph-checkpoint-sqlite | ≥3.0.0 | MIT |
| Core | langchain-anthropic | ≥0.2.0 | MIT |
| Core | anthropic | ≥0.40.0 | MIT |
| Core | python-dotenv | ≥1.0.0 | BSD-3 |
| Core | jsonschema | ≥4.20.0 | MIT |
| Dev | pytest | ≥8.0.0 | MIT |
| Dev | pytest-mock | ≥3.12.0 | MIT |
| Dev | pytest-cov | ≥4.1.0 | MIT |
| Dev | ruff | ≥0.5.0 | MIT |
| Dev | mypy | ≥1.10.0 | MIT |

**총 dependency 수**: Core 6 + Dev 5 = **11** (의도적 최소화)
