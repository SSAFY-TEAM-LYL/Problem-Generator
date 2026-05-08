# IPE 명세 보강 변경 내역 (Architect Review, 2026-05-07)

> 기존 `PROJECT_SPEC.md` (264줄) / `ARCHITECTURE.md` (1081줄)를 architect 관점에서 검토하여 누락된 기술 세부사항·병목·확장성 이슈를 식별하고 두 문서에 반영한 변경 요약. 이 문서는 **무엇이 새로 들어왔는지**만 정리합니다 (기존 본문 재기술 X).

---

## 0. 한눈에 보는 표

| Priority | 영역 | 기존 | 보강 후 | 적용 위치 |
|---|---|---|---|---|
| **P0** | 실행 격리 | `subprocess` 직접, RLIMIT/네트워크/FS 무통제 | 3-tier sandbox (Docker/nsjail/RLIMIT) + isolation self-test | SPEC §4.5.1, ARCH §3.9.0, §9.1 |
| **P0** | 루프 제어 | 글로벌 `max_iter=5`만 | per-node retry budget + `iteration_history` + 4종 termination | SPEC §5, ARCH §3.4, §3.9.5 |
| **P0** | 복구 | 단일 프로세스, 크래시 시 통째 손실 | LangGraph `SqliteSaver` checkpointer + `--resume` | SPEC §1·§5, ARCH §0·§3.4 |
| **P1** | 병렬화 | 강제 직렬 | Auditor‖Generator fan-out + Phase B/C `ThreadPoolExecutor` | SPEC §4.5, ARCH §3.4·§3.9.4 |
| **P1** | 제약조건 | 자유 문자열만 | `constraints_structured` (variables/time_limit_ms/memory_limit_mb) + Architect 검증 게이트 | SPEC §2·§4.1, ARCH §3.5 |
| **P1** | 비용 가드 | 추적 없음 | `LLMCallTracker` + `state["llm_calls"]` + `max_cost_usd` 가드 | SPEC §2·§7, ARCH §3.12·§9.2 |
| **P1** | 재현성 | LLM 응답 비결정·재현 불가 | `outputs/<run_id>/llm_traces/` + `--replay` 모드 | SPEC §6, ARCH §2·§9.3 |
| **P1** | 관측성 | 미명시 | 구조적 메트릭 표준 + (옵션) LangSmith/OTel hook | ARCH §3.12·§9.4 |
| **P1** | 난이도 분산 | 단일 LLM judgment, 분산 큼 | calibration anchor set + `difficulty_calibration_anchors` | SPEC §4.6, ARCH §3.10 |
| **P1** | 정해 성능 | "OK이면 통과" — 느린 정답이 oracle로 박제 가능 | Phase C 후 `wall_time ≤ time_limit × 0.5` 게이트 | SPEC §4.5, ARCH §3.9.5 |
| **P1** | adversarial 검증 | input이 constraints에 부합하는지 미검증 | Phase B 전 syntactic validator → Auditor로 라우팅 | SPEC §4.5, ARCH §3.9.5 |
| **P2** | special judge | stdout exact match만 | `has_special_judge` + special_judge 노드 (옵셔널) | SPEC §2·§4.1, ARCH §8 |
| **P2** | 중복 검출 | 없음 | `outputs/index.jsonl` (algo + embedding) | ARCH §2·§8 |
| **P2** | 난이도 ensemble | 단일 평가자 | 다수 평가자 투표 (future hook) | SPEC §4.6·§8, ARCH §8 |

---

## 1. ProblemState 신규/확장 필드

| 필드 | 타입 | 목적 |
|---|---|---|
| `run_id` | str (uuid) | checkpointer/trace 식별자 |
| `node_retry_budget` | `NodeRetryBudget` | 노드별 잔여 재시도 (architect 2 / coder 3 / auditor 2 / generator 2) |
| `max_cost_usd` | float | 비용 가드 (기본 5.0) |
| `constraints_structured` | `ConstraintSpec` | Executor enforce용 구조화 객체 (variables / time_limit_ms / memory_limit_mb / raw) |
| `has_special_judge` | bool | multiple-valid-output 문제 여부 |
| `special_judge_code` | Optional[str] | checker.py (P2 — Future) |
| `iteration_history` | `List[IterationRecord]` | 시도 이력 — feedback에 동봉되어 oscillation 방지 |
| `llm_calls` | `List[LLMCallRecord]` | LLM 호출 누적 + 비용 추적 |
| `difficulty_calibration_anchors` | Optional[List[Dict]] | 사용된 anchor 샘플 ID 목록 |
| `final_status` | Literal | `success` / `max_iterations` / `budget_exhausted` / `cost_exceeded` |

신규 보조 TypedDict 4개 추가:
- `ConstraintSpec` — 구조화된 제약조건
- `IterationRecord` — 시도 이력 한 항목
- `LLMCallRecord` — LLM 호출 한 건
- `NodeRetryBudget` — 노드별 잔여 budget

---

## 2. 신규/확장 모듈

| 경로 | 역할 |
|---|---|
| `ipe/sandbox/runner.py` | `SandboxedRunner` ABC + `RunSpec` / `RunResult` |
| `ipe/sandbox/docker_runner.py` | T1: Docker 컨테이너 (`--network=none --read-only --tmpfs --memory --cpus --pids-limit`) |
| `ipe/sandbox/nsjail_runner.py` | T2: nsjail/firejail/bubblewrap |
| `ipe/sandbox/rlimit_runner.py` | T3: `setrlimit` only (호환성 fallback) |
| `ipe/observability.py` | `LLMCallTracker` / `ReplayTracker` / 가격표 / 메트릭 표준 |
| `ipe/calibration/anchors.json` | 백준 표준 난이도별 reference 샘플 (Bronze5 ~ Ruby1) |

---

## 3. 신규 산출물 구조

```
outputs/<run_id>/
├─ ... (기존 항목)
├─ llm_traces/              # 신규 — 모든 LLM 호출 raw 입출력
│  └─ <seq>_<node>.json     #   {seq, node, model, system, user, response, tokens, cost_usd, ts}
└─ checkpoint.db            # 신규 — LangGraph SqliteSaver

outputs/
└─ index.jsonl              # P2 — 중복 검출용 (algo, title, embedding)
```

`problem.json` 신규 필드:
- `meta.run_id`, `meta.sandbox_tier`, `meta.sandbox_isolation_pass`
- `meta.llm_call_summary` (총 호출 수 / 토큰 / 비용 / 노드별 분포)
- `constraints_structured` (top-level)
- `difficulty.calibration_anchors`
- `iteration_history` (top-level)
- `llm_calls` (top-level)

---

## 4. CLI 옵션 추가

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--sandbox <auto\|docker\|nsjail\|rlimit>` | `auto` | 격리 tier 선택 |
| `--strict-sandbox` | off | isolation_self_test 실패 시 즉시 abort |
| `--max-cost-usd <N>` | 5.0 | 비용 가드 임계 |
| `--cost-warn-usd <N>` | (없음) | 경고 임계 (halt X) |
| `--exec-workers <N>` | 4 | Phase B/C ThreadPoolExecutor worker 수 |
| `--parallel-fanout` | off | Auditor‖Generator 병렬 (P1 옵션) |
| `--resume <run_id>` | — | SqliteSaver에서 복구 |
| `--replay <run_id>` | — | LLM 호출 cache hit (비용 0) |

---

## 5. 가드레일 우선순위 (동시 트리거 시 적용 순서)

1. `sandbox_isolation_pass=false` (with `--strict-sandbox`) → 즉시 abort
2. `cost_exceeded` (가장 비싸므로 먼저 차단)
3. `budget_exhausted` (per-node)
4. `max_iterations` (글로벌 안전망)
5. `success` (정상 종료)

`final_status`는 set-once semantics — 한 번 set되면 후속 노드에서 덮어쓰지 않음.

---

## 6. 기존 본문 변경된 항목

기존 내용을 **수정**한 부분 (신규 항목과 별개):

| 위치 | Before | After |
|---|---|---|
| SPEC §4.5 Phase A | "stdout == expected (정확 일치)" | special_judge_code 분기 추가 |
| SPEC §4.5 Phase B | "RTE/TLE 없음" | + adversarial input이 `constraints_structured`에 부합하는지 syntactic validator |
| SPEC §4.5 Phase C | "RTE/TLE 없음" | + 정해 wall_time ≤ `time_limit × 0.5` 게이트 |
| SPEC §4.5 Executor 환경 | "Python `subprocess` + Local OS" | "Python `subprocess` + Sandboxed Runner" |
| SPEC §6 outputs 폴더명 | `<timestamp>_<algo>/` | `<run_id>/` (timestamp_algo는 별칭 심볼릭 링크) |
| ARCH §3.9 도입부 | "물리적으로 코드를 컴파일/실행" | "**격리 환경(sandbox)에서** 물리적으로 컴파일/실행" |
| ARCH §3.4 graph.py | `route_after_executor` — global iter만 검사 | + cost guard + per-node budget 검사 |

---

## 7. 의도적으로 P2(Future)로 남긴 항목

이번 라운드에서 본문 반영하지 않고 §8 확장 포인트에만 언급:

- Sub-agent 분해 (Story_Agent / Constraint_Agent)
- 새 언어 지원 (C++, Rust, Go) — sandbox 이미지 toolchain 추가 필요
- Special judge 노드 구현체 (state 필드만 마련)
- Brute-force cross-check (Coder가 골든+브루트포스 둘 다 작성)
- 난이도 ensemble (다수 평가자 투표)
- 중복/유사문제 detection 구현체 (`outputs/index.jsonl` 경로만 예약)
- Cost-aware model routing (Sonnet → Opus escalation)
- Multi-language oracle cross-check
- Persistent JVM (GraalVM/nailgun)

---

## 8. 미해결 / 후속 논의 필요 (Round 1 시점)

- **Sandbox 디폴트 정책**: MVP `auto`(T2 우선)로 합의했지만, CI/CD 환경에서는 `--sandbox docker`가 더 안전. `Dockerfile` 또는 `compose.yml` 동봉 여부는 별도 작업. → **Round 2에서 재결정** (Q2 = Cross-platform, T1 권장).
- **Calibration anchors 큐레이션**: `anchors.json` 초기 콘텐츠를 누가 어디서 가져올지 (백준 공개 문제 라이선스 고려). 본 변경은 스키마/로딩 메커니즘만 정의.
- **LLM 가격 갱신**: `observability.py:PRICING`은 단일 진실원이지만 모델 업데이트 시 수동 갱신 필요. 외부 가격 fetcher는 향후 작업.
- **`--replay` 매칭 전략**: 현재 설계는 seq 순서 기반. 메시지 해시 기반 매칭이 더 robust하지만 프롬프트 수정 시 모든 trace가 무효화됨 — 트레이드오프 결정 필요.

---

## 9. Round 2 — REVIEW_REPORT 기반 수정 (2026-05-08)

> 외부 리뷰([`archive/REVIEW_REPORT_2026-05-07.md`](archive/REVIEW_REPORT_2026-05-07.md), 2026-05-07 작성, Round 4에서 archive로 이동)가 Round 1 결과물에서 식별한 문제들을 **메타 검증 후** 반영. 메타 검증 결과는 본 세션 대화에 기록됨 (CRITICAL 3건 100% 사실 / WARNING 4건 중 2건 사실 + 2건 valid concern / MINOR 2건 — M1 규모는 과장이었으나 분리는 채택).

### 9.1 CRITICAL 수정 (문서 일관성)

| # | 변경 | 영향 |
|---|---|---|
| **C1** | `ARCHITECTURE.md` §3.11의 `outputs/<timestamp>_<algo>/` 경로를 `outputs/<run_id>/`로 통일. `<timestamp>_<algo>`는 `outputs/by-name/`에 별칭 symlink로만 잔존. `save_result()` 코드 예시도 `state["run_id"]` 사용으로 갱신. | sandbox·checkpointer·llm_traces가 동일 식별자(`run_id`)를 사용 → 일관성 회복. |
| **C2** | `ARCHITECTURE.md` §6의 인라인 `problem.json` 구버전 스키마 삭제. SPEC §6을 SSOT로 명시하고 ARCH §6은 **DB 매핑 관점**(테이블, inline/manifest, 인덱싱)만 다룬다. | 충돌 스키마 제거. 신규 테이블 추가: `iteration_history`, `llm_calls`. |
| **C3** | `ARCHITECTURE.md` §3.10 Evaluator의 `def run` 이중 정의 통합. Calibration anchor 포함 버전을 단일 정의로 유지 (구버전 블록 제거). `import json` 추가 + 반환 dict에 `difficulty_calibration_anchors` 포함. | CLI 구현 모호성 해소. |

### 9.2 WARNING 수정 (구현 안전성)

| # | 변경 | 영향 |
|---|---|---|
| **W1** | `PROJECT_SPEC.md` §4.5.1 sandbox 정책 재구성. **신규 Tier T2.5** (macOS sandbox-exec) 추가. T2를 Linux 전용으로 명시. OS별 자동 선택 표 (`Linux: T1→T2→T3`, `macOS: T1→T2.5→T3+경고`, `Windows: T1→T3+경고`) 추가. macOS 개발 환경 주의사항 별도 명시. | 사용자 OS = macOS이므로 즉시 영향. nsjail/firejail 거짓 작동 가정 제거. |
| **W3** | Phase A 휴리스틱 **3-way 분기**로 확장. 신규 분기: "전체 sample 실패 + 컴파일 OK + 솔루션이 모든 sample에서 일관된 출력 생성" → Architect (sample 전체가 잘못됐을 가능성). `iteration_history`의 `error_signature`를 활용한 자동 분기 전환 명시. | 잘못된 sample이 정답 솔루션을 깨뜨리는 false-negative 차단. |
| **W2** (선택적 보강) | `ARCHITECTURE.md` §3.5에 **Anthropic `tool_use` API 활용 보강안** 추가. `architect_tool` 정의 + `bind_tools()` 패턴 + `jsonschema.validate()` fallback. MVP는 prompt-only로 시작, 누락률 >5%이면 tool_use로 전환. | `constraints_structured` 누락 발생 시 대응 경로 명문화. |
| **W4** (선택적 보강) | `ARCHITECTURE.md` §3.9.5에 **명시적 oscillation 방지 프롬프트 패턴** 추가. `_build_history_section()` 헬퍼 + 동일 `error_signature` 2회 반복 시 자동 강한 경고 삽입. | LLM이 history를 무시하고 같은 fix를 반복하는 위험 완화. |

### 9.3 MINOR 수정 (문서 품질)

| # | 변경 | 영향 |
|---|---|---|
| **M1** | **신규 파일 [`PYTHON_GUIDE.md`](PYTHON_GUIDE.md) 생성**. ARCH §4 (Python 문법), §5 (LangGraph 패턴), §7 (흔한 실수) + 모듈별 산재된 "Python 문법 노트" 박스를 통합. ARCH 본문은 짧은 redirect 링크로 교체. | ARCH ~1490줄 → ~1080줄 (-410줄), PYTHON_GUIDE ~210줄 신규. CLI 에이전트 컨텍스트 효율 향상. <br>**참고:** REVIEW가 주장한 "400줄 혼재"는 §4-7만 기준으로는 ~66줄이었음 (메타 검증 시 정정). 모듈별 박스를 통합한 결과 실제 분리량은 ~210줄 수준. |
| **M2** | `ARCHITECTURE.md` §3.3.0 신규 — **모델명 ↔ API ID 표준 매핑 표 (SSOT)**. SPEC §4 도입부에 "코드/설정/trace는 ARCH §3.3.0의 API ID를 사용"이라는 안내 추가. | SPEC=마케팅명, ARCH=API ID로 분리되어 있던 명명 정책을 단일 표로 통일. |

### 9.4 Q1~Q5 결정 반영

`PROJECT_SPEC.md` §1.5 신설 — **Design Decisions** 표로 5개 결정 영구 기록.

| # | 결정 | 본문 반영 위치 |
|---|---|---|
| Q1 | LangGraph 유지 | SPEC §1, §1.5 |
| Q2 | Cross-platform (Docker 권장 + OS별 fallback) | SPEC §1, §1.5, §4.5.1 |
| Q3 | Python 교육 분리 (`PYTHON_GUIDE.md`) | 신규 파일, ARCH §4·§7 redirect |
| Q4 | `problem.json` SSOT = SPEC §6 | ARCH §6 보조 매핑 표 + cross-link |
| Q5 | coder 3→4, max_iter 5→7 | SPEC §5, ARCH §3.4 (`DEFAULT_NODE_BUDGET`, `DEFAULT_MAX_ITER`) |

### 9.5 신규/축소된 파일 (실측치)

| 파일 | Round 1 끝 | Round 2 끝 | Δ |
|---|---|---|---|
| `PROJECT_SPEC.md` | 433줄 | 472줄 | +39 (Q1-Q5 §1.5, sandbox OS 표, retry budget 갱신, M2 안내) |
| `ARCHITECTURE.md` | 1485줄 | 1460줄 | -25 (제거: §6 인라인 스키마 -60줄, §3.10 dedup -28줄, §4·§5·§7 redirect -49줄. 추가: W2 tool_use +30, W4 oscillation +30, W3 3-way 휴리스틱 +10, §3.3.0 매핑표 +15, §3.11 run_id 보강 +15, §6 DB 매핑 +30 등 ~+130) |
| `PYTHON_GUIDE.md` | (없음) | 215줄 | +215 (신규) |
| `CHANGES.md` | 152줄 | 213줄 | +61 (본 §9) |

> **노트:** ARCH 감소폭이 예측(-405)보다 작은(-25) 이유는 WARNING 보강(W2/W3/W4)과 신규 §3.3.0/§3.11 보완 컨텐츠가 동시에 추가됐기 때문이다. 순수 제거(-137줄) 대비 신규 안전 가드 컨텐츠(+~130줄)가 들어왔다 — 즉 **품질·안전성 측면에서 ARCH는 더 충실해졌고**, 별도로 PYTHON_GUIDE.md(215줄)가 분리되어 CLI 컨텍스트 효율도 확보.

### 9.6 메타 검증 결과 (참고)

리뷰 리포트의 주장 검증 (사용자 요청에 따라 수행):

- ✅ **CRITICAL 3건 모두 사실** — grep으로 검증 완료
- ✅ **W1, W3 사실** — 즉시 수정 가치
- 🟡 **W2, W4 valid concern이지만 문서 결함은 아님** — 권장 보강으로만 추가
- ⚠️ **M1 수치 과장** — "400줄"은 §4-7 기준 실제 ~66줄 (모듈별 박스 포함 시 ~210줄)
- 🟡 **M2 부분 사실** — 단일 문서 내 혼용은 미미, 문서 간 단위 차이는 사실
- ❓ **Q1-Q5 valid한 미결정 사항** — 사용자 답변 후 본문 반영

---

## 10. Round 3 — Implementation Roadmap 신설 (2026-05-08)

> 사용자 지시: "개선된 아키텍처를 바탕으로 프로젝트 명세를 구체화. planner 에이전트가 실제 구현 단계를 쪼갤 수 있을 정도로 상세한 로드맵과 파일 구조를 추가."
>
> /plan 응답에서 사용자가 두 modification을 선택: **(1) 별도 파일로 분리, (2) phase를 더 쪼갬**. → 신규 파일 `IMPLEMENTATION_ROADMAP.md`로 12-phase 로드맵 작성.

### 10.1 신규 파일: `IMPLEMENTATION_ROADMAP.md`

**목적**: planner 에이전트가 본 문서를 받아 즉시 sprint/task로 분해 가능하도록 작성된 12-phase 로드맵.

**구조** (8 섹션):

| 섹션 | 내용 |
|---|---|
| §0 | 12-phase 한눈에 보는 표 (총 17.5일 예상) |
| §1 | Phase 상세 — P0~P12 각각 (목표·산출물·sub-tasks·DoD·테스트·핸드오프) |
| §2 | 파일 책임 매트릭스 — 30+ 파일의 line budget·핵심 함수·의존·작성 phase |
| §3 | 의존성 그래프 (ASCII) + critical path + 2인 페어 병렬 가능 표시 |
| §4 | 테스트 전략 매트릭스 (단위/통합/격리/E2E × LLM 비용 × 의존) |
| §5 | 부트스트랩 가이드 — `requirements.txt`, `pyproject.toml`, `.env.example`, `Makefile`, `Dockerfile`, `.github/workflows/ci.yml` 견본 |
| §6 | 위험·완화책 표 (7건) |
| §7 | 다음 라운드 (out of scope) — sub-agent 분해 등 P13+ 후보 |
| §8 | planner 에이전트를 위한 메모 (Phase=Sprint, Sub-task=Ticket 매핑 가이드) |

### 10.2 12-Phase 분해 (Round 1 plan의 6-phase에서 세분화)

| Round 1 plan | Round 3 (실제) |
|---|---|
| P0 기반·부트스트랩 | **P0** Bootstrap (0.5일) |
|  | **P1** Sandbox Foundation (2.0일) |
|  | **P2** LLM Layer (1.0일) |
| P1 Coder + Executor 최소회로 | **P3** Coder + Executor 최소회로 (1.5일) |
| P2 Architect + Phase A | **P4** Architect + Phase A 3-way (1.5일) |
| P3 Auditor + Generator + Phase B/C | **P5** Auditor + Phase B (1.5일) |
|  | **P6** Generator + Phase C (2.0일) |
| P4 Routing·iteration·cost guard | **P7** Routing & Retry Discipline (1.5일) |
|  | **P8** Checkpointing & Replay (1.5일) |
| P5 Evaluator + io.py + 관측성 | **P9** Evaluator + Calibration (1.0일) |
|  | **P10** Output Persistence (1.0일) |
|  | **P11** Observability (1.0일) |
|  | **P12** Tests + CLI + CI (2.0일) |

→ **6 phase → 12 phase로 분해**. 각 phase 1~3일 단위, sub-task 0.5~4h 단위.

### 10.3 핵심 산출물 약속 (DoD-derivable)

본 로드맵을 따르면:
- 30개 모듈 / ~4,800줄 (테스트 제외) — 800줄 초과 파일 0개
- 800줄 절대 상한 / 600줄 권장 상한 — `executor.py`만 620줄로 가장 큼
- 단위·통합·격리·E2E 4-tier 테스트, 합산 80%+ 커버리지
- Linux + macOS CI matrix
- macOS 사용자 환경 우선 검증 (T2.5 sandbox-exec + T1 Docker)
- 단일 개발자 ~3.5주 / 2인 페어 ~12일 예상

### 10.4 PROJECT_SPEC.md cross-link 추가

`PROJECT_SPEC.md` §1과 §1.5 사이에 `IMPLEMENTATION_ROADMAP.md` 안내 blockquote 1줄 추가. SPEC 본문은 변경 X (구현 가이드는 별도 문서로 분리, Round 1·2 결정사항 그대로 유지).

### 10.5 파일 라인 수 변화 (Round 2 → Round 3)

| 파일 | Round 2 끝 | Round 3 끝 | Δ |
|---|---|---|---|
| `PROJECT_SPEC.md` | 472줄 | 474줄 | +2 (cross-link blockquote) |
| `IMPLEMENTATION_ROADMAP.md` | (없음) | ~660줄 | +660 (신규) |
| `CHANGES.md` | 213줄 | ~290줄 | +77 (본 §10) |
| `ARCHITECTURE.md` | 1460줄 | 1460줄 | 0 (변경 없음) |
| `PYTHON_GUIDE.md` | 215줄 | 215줄 | 0 (변경 없음) |

### 10.6 Round 3에서 의도적으로 하지 않은 것

- **ARCHITECTURE.md 변경 없음** — 코드 설계는 이미 완료. 로드맵은 그 설계를 *순서대로 만드는 방법*만 정의.
- **task-level까지 분해하지 않음** — sub-task 단위(0.5~4h)까지만 정의. 그 이하 분해는 planner 에이전트의 몫.
- **실제 코드 작성 0** — 본 라운드는 명세·로드맵 문서화만. 실제 P0~P12 구현은 별도 라운드.
- **anchors.json 콘텐츠 미작성** — P9 sub-task로 명시. 본 라운드에서는 schema와 로딩 메커니즘 정의만.
- **테스트 fixture 미작성** — `tests/fixtures/llm_responses/<phase>/<scenario>.json`은 P3+ 각 phase에서 작성.

---

## 11. Round 4 — REVIEW_REPORT 아카이브 (2026-05-08)

> 사용자 지시: "필요 없을만한 파일들이 있나?" → 분석 후 옵션 A ("REVIEW_REPORT만 archive") 채택.

### 11.1 변경 내용

| 변경 | Before | After |
|---|---|---|
| 파일 이동 | `REVIEW_REPORT.md` (workspace 루트) | `archive/REVIEW_REPORT_2026-05-07.md` |
| `archive/` 디렉토리 신설 | 없음 | 생성 |
| CHANGES.md §9.1 도입부 경로 링크 갱신 | `` `REVIEW_REPORT.md` `` (인라인 코드) | `[archive/REVIEW_REPORT_2026-05-07.md](archive/REVIEW_REPORT_2026-05-07.md)` (markdown link) |

### 11.2 보존된 인용

REVIEW_REPORT 본문은 **활성 워크스페이스 외부**로 이동했지만, "REVIEW_REPORT W1", "REVIEW_REPORT M2", "REVIEW_REPORT 기반" 등의 **개념적 인용**(파일 경로 아닌 출처 표시)은 SPEC/ARCH/PYTHON_GUIDE에 그대로 보존. 9건. 이는 결정의 출처를 추적 가능하게 유지하기 위함.

### 11.3 archive 정책

- `archive/<NAME>_<YYYY-MM-DD>.md` 패턴.
- 활성 의사결정 입력에서 제외된 문서가 들어감 (이미 처리됨, 더 이상 행동 없음).
- 새 합류자에게는 "활성 5개 + archive 1개" 구조가 "이건 역사 참고용" 신호로 작동.

### 11.4 활성 워크스페이스 (Round 4 종료 시점)

| 파일 | 줄 수 | 역할 |
|---|---|---|
| `PROJECT_SPEC.md` | 474 | 요구사항·결정 SSOT |
| `ARCHITECTURE.md` | 1460 | 코드 설계 |
| `IMPLEMENTATION_ROADMAP.md` | 749 | 12-phase 로드맵 |
| `PYTHON_GUIDE.md` | 215 | Python/LangGraph 문법 (선택적) |
| `CHANGES.md` | ~320 | Round 1~4 변경 이력 |
| `archive/REVIEW_REPORT_2026-05-07.md` | 210 | 외부 리뷰 (archival, Round 2 입력) |

활성 6 → 5로 정리. archive 1건 신설.

---

## 12. Round 5 — Phase-branch 워크플로 도입 (2026-05-08)

> 사용자 지시: "이제부터 각 페이즈별로 별도 브랜치에서 작업하고 합치도록 하자. 이전의 내역들도 그렇게 수정해보는건 어떄?"
>
> /plan에서 3가지 옵션 제시 (A: historical reference / B: full rewrite + force push / C: forward only). 사용자가 권장 옵션 A 선택 → "권장하는 옵션대로 진행해".

### 12.1 변경 내용

#### Historical phase branches (force push 없이 안전하게)

main의 commit history는 **그대로 보존**, 각 phase 완료 시점 commit에 branch reference만 추가:

| Branch | 가리키는 commit | 의미 |
|---|---|---|
| `feat/p0-bootstrap` | `83e6bbf` | P0 Bootstrap 완료 시점 |
| `feat/c-readme` | `ef2f64b` | README 추가 (Round 5의 "C" 단계) |
| `feat/p1-sandbox` | `3f8d7bb` | P1 Sandbox Foundation 완료 시점 |

세 branch 모두 원격에 push 완료. main과 동일 history를 공유하지만 phase 단위 navigate 가능.

### 12.2 앞으로의 워크플로 (P2부터)

```bash
# 1. Phase 시작
git checkout main
git pull
git checkout -b feat/p2-llm-layer

# 2. Sub-task별 commit
# (현재처럼 P2.1, P2.2, ... 작업)

# 3. Phase 끝나면 push
git push -u origin feat/p2-llm-layer

# 4. (옵션) GitHub PR 생성 → review → merge
gh pr create --base main --head feat/p2-llm-layer --title "feat(p2): LLM Layer"
gh pr merge --merge   # --no-ff (merge commit 생성, phase 경계 명시)

# 5. main 동기화
git checkout main
git pull
```

### 12.3 Merge 정책

**`--no-ff` (merge commit 생성)** 채택. 이유:
- main에 phase 경계가 merge commit으로 명시됨 (history 가독성)
- `git log --first-parent main`으로 phase-level 요약 가능
- squash와 달리 sub-task별 commit history 보존

대안 (채택 X):
- `--squash`: sub-task history 압축 — 가독성↓ debugging↓
- `ff-only`: linear history — branch의 의미 약해짐

### 12.4 PR vs 직접 merge

**선택**: GitHub PR 사용 (CI/리뷰 채널이 명확). 단일 개발자에게는 약간의 오버헤드지만:
- diff 검토 가능
- 미래 multi-developer 확장 용이
- GitHub UI history navigate 명확

CI 통과 안 되면 merge 차단 (P12 GitHub Actions 도입 후).

### 12.5 force push 회피 근거

기존 commit history (Round 1~4)를 force push로 재작성하지 않은 이유:
- 이미 GitHub origin에 push된 commits — force push 시 다른 clone (없더라도 향후 가능성) 충돌
- Round 1~4 정합성은 이미 검증됨 (P0/P1 DoD 통과)
- 가벼운 reference만으로도 phase 단위 navigate 가능

향후 진짜 phase-격리 history가 꼭 필요하면 별도 라운드에서 검토.
