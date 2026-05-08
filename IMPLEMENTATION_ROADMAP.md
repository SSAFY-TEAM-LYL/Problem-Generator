# IPE Implementation Roadmap

> **목적**: planner 에이전트(또는 인간 lead)가 본 문서를 받아 즉시 sprint/task 단위로 분해할 수 있도록, 12개의 phase × 2~5 sub-task로 구체화된 로드맵.
>
> **선행 문서**:
> - 요구사항·결정사항: [`PROJECT_SPEC.md`](PROJECT_SPEC.md)
> - 코드 설계: [`ARCHITECTURE.md`](ARCHITECTURE.md)
> - 문법 참고: [`PYTHON_GUIDE.md`](PYTHON_GUIDE.md)
>
> **사용 방식**: 각 phase는 **1~3일 작업 단위** (1인 기준). sub-task는 **0.5~4h 단위**. planner는 phase를 sprint로, sub-task를 ticket으로 매핑하면 된다.
>
> **불변 규칙**: phase 의존성을 무시하고 점프 금지. P_n은 P_{<n}의 DoD가 모두 충족된 뒤 시작.

---

## 0. 한눈에 보는 12-Phase 표

| # | Phase 이름 | 핵심 산출물 | 예상 (일) | 의존 |
|---|---|---|---|---|
| **P0** | Bootstrap | pyproject, deps, state.py, Makefile | 0.5 | — |
| **P1** | Sandbox Foundation | runner ABC + 4 tier 구현 + selector | 2.0 | P0 |
| **P2** | LLM Layer | get_chat, JSON 파서, LLMCallTracker | 1.0 | P0 |
| **P3** | Coder + Executor 최소회로 | coder.py + executor.py (compile + Phase A skeleton) | 1.5 | P1, P2 |
| **P4** | Architect + Phase A 라우팅 | architect.py + Phase A 3-way 휴리스틱 | 1.5 | P3 |
| **P5** | Auditor + Phase B | auditor.py + syntactic validator + oracle baseline | 1.5 | P4 |
| **P6** | Generator + Phase C | generator.py + 시드 stress + 병렬 case + 정해 50% 게이트 | 2.0 | P5 |
| **P7** | Routing & Retry Discipline | route_after_executor + budget + iteration_history + cost guard | 1.5 | P6 |
| **P8** | Checkpointing & Replay | SqliteSaver + --resume + ReplayTracker + --replay | 1.5 | P7 |
| **P9** | Evaluator + Calibration | anchors.json + evaluator.py | 1.0 | P8 |
| **P10** | Output Persistence | io.py + manifest + by-name symlink + problem.md | 1.0 | P9 |
| **P11** | Observability | structured logging + 메트릭 + (옵션) LangSmith/OTel | 1.0 | P10 |
| **P12** | Tests + CLI + CI | unit/integration/sandbox/e2e + main.py + GitHub Actions | 2.0 | P11 |
| | **TOTAL** | | **17.5일** | |

> **단일 개발자 풀타임 기준 ~3.5주.** 2인 페어로는 ~2주. 환경 이슈로 +20% 버퍼 권장.

---

## 1. Phase 상세

각 phase는 다음 6개 항목으로 구성:
- **목표** (한 문단)
- **산출물** (생성/수정 파일)
- **Sub-tasks** (planner ticket 단위)
- **Definition of Done** (체크리스트)
- **테스트 전략**
- **다음 phase로의 핸드오프 조건**

---

### P0 — Bootstrap (0.5일)

**목표**: 패키지 import만 되고 타입 체크가 통과되는 최소 skeleton. 아직 LLM도 sandbox도 호출 안 함.

**산출물**:
- `pyproject.toml` — 패키지 메타, entry_points, ruff/mypy 설정
- `requirements.txt` — `langgraph`, `langchain-anthropic`, `anthropic`, `python-dotenv`, `jsonschema`, `pytest`, `pytest-mock`, `pytest-cov`, `ruff`, `mypy`
- `.env.example` — `ANTHROPIC_API_KEY=`, `IPE_SANDBOX=auto`, `IPE_MAX_COST_USD=5.0`
- `.gitignore` — `outputs/`, `workdir/`, `__pycache__/`, `.env`, `*.egg-info`
- `ipe/__init__.py` (빈)
- `ipe/state.py` — `ProblemState`, `ConstraintSpec`, `IterationRecord`, `LLMCallRecord`, `NodeRetryBudget` TypedDict (스펙 §2 그대로)
- `ipe/nodes/__init__.py` (빈)
- `ipe/sandbox/__init__.py` (빈)
- `tests/__init__.py`, `tests/test_state.py` — TypedDict import smoke
- `Makefile`

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P0.1 | pyproject + requirements + .gitignore + .env.example | 1h |
| P0.2 | ipe/state.py (TypedDict 5개) + import smoke test | 2h |
| P0.3 | Makefile (`make install`, `make test`, `make lint`) + ruff/mypy 설정 | 1h |

**Definition of Done**:
- [ ] `pip install -e .` 성공
- [ ] `python -c "from ipe.state import ProblemState"` 성공
- [ ] `pytest` 1개 통과
- [ ] `ruff check .` 0 issue
- [ ] `mypy ipe/` 0 error
- [ ] `make install && make lint && make test` 한 줄로 통과

**테스트**:
- 단위: `tests/test_state.py` (TypedDict 키 존재 verify)

**핸드오프**: state.py가 안정 — P1~P12 어디서든 `from ipe.state import ProblemState` 가능.

---

### P1 — Sandbox Foundation (2.0일)

**목표**: 격리 실행 레이어를 가장 먼저 구현. **사용자 OS = macOS** 가정 → T2.5(sandbox-exec)와 T1(Docker) 우선 검증.

**산출물**:
- `ipe/sandbox/runner.py` — `SandboxedRunner` ABC + `RunSpec`/`RunResult` dataclasses
- `ipe/sandbox/rlimit_runner.py` — T3 fallback (cross-platform)
- `ipe/sandbox/sandboxexec_runner.py` — T2.5 macOS sandbox-exec
- `ipe/sandbox/docker_runner.py` — T1 Docker
- `ipe/sandbox/nsjail_runner.py` — T2 Linux (Linux 머신 없으면 stub + `pytest.skip(if not Linux)`)
- `ipe/sandbox/selector.py` — `pick_runner(tier_arg, platform)`
- `ipe/sandbox/__main__.py` — `python -m ipe.sandbox` selftest CLI
- `Dockerfile` — sandbox baseline image (Python 3.11 + JDK 17)
- `tests/sandbox/test_isolation.py` — network/FS/fork 위반 차단 검증

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P1.1 | runner.py: ABC + RunSpec/RunResult + status enum | 2h |
| P1.2 | rlimit_runner.py: setrlimit + subprocess wrapper + stdout/stderr cap | 3h |
| P1.3 | sandboxexec_runner.py: profile 동적 생성 + sandbox-exec invoke | 3h |
| P1.4 | docker_runner.py: docker run 옵션 조합 + image build | 4h |
| P1.5 | selector.py + Dockerfile + selftest CLI | 2h |
| P1.6 | tests/sandbox/test_isolation.py: 5개 시나리오 | 2h |

**Definition of Done**:
- [ ] `python -m ipe.sandbox --tier rlimit` 통과 (모든 OS)
- [ ] `python -m ipe.sandbox --tier sandboxexec` 통과 (macOS)
- [ ] `python -m ipe.sandbox --tier docker` 통과 (Docker Desktop 시)
- [ ] `socket.gethostbyname("google.com")`이 T1/T2.5에서 차단됨
- [ ] `/etc/passwd` 읽기 시도가 T1에서 차단됨
- [ ] fork bomb이 `RLIMIT_NPROC` 또는 `--pids-limit`에 의해 제한됨
- [ ] 무한 루프 솔루션이 TLE로 종료
- [ ] 1GB alloc이 MLE로 종료

**테스트**:
- 단위: 각 Runner의 `run()` (mock subprocess)
- 통합: `test_isolation.py` (실제 subprocess, `@pytest.mark.slow`)

**핸드오프**: 어떤 노드든 `runner.run(spec)` 한 줄로 격리 실행 가능. **이 phase 통과 전까지 LLM도 호출하지 않는다** (보안 우선).

---

### P2 — LLM Layer (1.0일)

**목표**: Claude 호출 + JSON 파싱 + 비용·토큰 회계의 단일 진입점.

**산출물**:
- `ipe/llm.py` — `get_chat`, `parse_json_block`, `parse_json_array_field`
- `ipe/observability.py` — `LLMCallTracker`, `PRICING` (ARCH §3.3.0 매핑 표 기반)
- `tests/test_llm.py`, `tests/test_observability.py`

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P2.1 | llm.py: get_chat (temperature 동적 처리) | 2h |
| P2.2 | llm.py: parse_json_block + parse_json_array_field (state machine) | 3h |
| P2.3 | observability.py: PRICING + _cost_usd + LLMCallTracker | 2h |
| P2.4 | tests | 1h |

**Definition of Done**:
- [ ] `get_chat("claude-opus-4-7").invoke([...])` 성공
- [ ] `parse_json_block` — 펜스 안/바깥/잘못된 JSON 모두 처리
- [ ] `parse_json_array_field` — truncation된 응답에서 완성 entry만 복구
- [ ] `LLMCallTracker.invoke()` 호출 시 `state["llm_calls"]` 누적, `outputs/<run_id>/llm_traces/0001_<node>.json` 생성
- [ ] `PRICING`에 Opus 4.7 / Sonnet 4.6 / Haiku 4.5 단가 정의

**테스트**:
- 단위: parser edge cases (빈 응답, 펜스 없음, 절단)

**핸드오프**: 모든 노드가 `tracker.invoke(chat, messages, node="X", state_calls=state["llm_calls"])` 한 줄로 호출 가능.

---

### P3 — Coder + Executor 최소회로 (1.5일)

**목표**: LLM 1회 호출(Coder) → 격리 실행(Executor Phase A 단순) → stdout 비교 → OK/RTE/TLE 판정의 최소 사이클.

**산출물**:
- `ipe/nodes/coder.py` — fence parsing, IMPOSSIBLE 검출
- `ipe/nodes/executor.py` (1단계) — `_normalize`, `_write_source`, `_compile`, `_execute_solution`, Phase A 단순 (single sample)
- `tests/integration/test_minimal_circuit.py` — hardcoded problem.json → solution → Phase A

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P3.1 | coder.py: SYSTEM_PROMPT + USER_TEMPLATE + `_parse_response` (fence + IMPOSSIBLE) | 3h |
| P3.2 | executor.py: `_normalize`, `_write_source` (java/python), `_compile`, `_execute_solution` | 4h |
| P3.3 | executor.py: Phase A skeleton (단일 sample, exact match) | 2h |
| P3.4 | 통합 테스트: hardcoded "두 수의 합"으로 round-trip | 3h |

**Definition of Done**:
- [ ] hardcoded problem (`A+B`)을 입력 → Coder가 정답 코드 반환
- [ ] Java + Python 둘 다 컴파일/실행 성공
- [ ] sample input "1 2" → expected "3" 일치 검증
- [ ] 의도적 syntax error → `compile_err` 반환
- [ ] 의도적 무한 루프 → TLE 반환

**테스트**:
- 단위: coder._parse_response (fence 우선순위, IMPOSSIBLE 검출)
- 통합: mock LLM(고정 응답) + 실제 sandbox + 실제 컴파일

**핸드오프**: Phase A 단순형 동작. P4에서 휴리스틱 라우팅 추가.

---

### P4 — Architect + Phase A 3-way 라우팅 (1.5일)

**목표**: Architect가 문제·constraints_structured·sample_testcases를 생성. Phase A가 3-way 휴리스틱으로 분기.

**산출물**:
- `ipe/nodes/architect.py` — SYSTEM_PROMPT, `_validate_constraints_structured`, `run`
- `ipe/nodes/executor.py` (확장) — Phase A 3-way 휴리스틱
- `ipe/graph.py` (skeleton) — START → architect → coder → executor (직선, 라우팅은 P7)
- `main.py` (minimal) — `--algorithm`, `--language` 인자 처리

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P4.1 | architect.py: prompts + `_validate_constraints_structured` (jsonschema) | 3h |
| P4.2 | executor.py: Phase A 3-way 휴리스틱 | 3h |
| P4.3 | graph.py 골격: 직선 edge만 | 1h |
| P4.4 | main.py: minimal CLI + 첫 cycle 실행 | 2h |
| P4.5 | 통합 테스트 + algorithm="A+B" 1 cycle 성공 | 3h |

**Definition of Done**:
- [ ] `architect.run({"target_algorithm": "Two Sum"})` → problem_title, problem_description, constraints, constraints_structured, sample_testcases (3+개), has_special_judge 모두 채움
- [ ] `constraints_structured` 누락 시 `ValueError` → feedback과 함께 self-loop
- [ ] Phase A 3-way 휴리스틱:
  - 5개 중 4개 통과 → Architect
  - 전체 실패 + 컴파일 OK + 일관 출력 → Architect (REVIEW W3)
  - 다수 실패 + 크래시 동반 → Coder
- [ ] `python main.py --algorithm "Two Sum" --language python` → 문제 + 정해 1차 산출

**테스트**:
- 단위: `_validate_constraints_structured` (정상/누락/타입오류)
- 통합: mock LLM 응답 3종 (정상, 누락, 부분실패)

**핸드오프**: 정상 cycle 1회 동작. 실패 라우팅은 graph 직선이라 halt → P7에서 완성.

---

### P5 — Auditor + Phase B + Syntactic Validator (1.5일)

**목표**: Auditor가 적대적 input 8~15개 생성, Phase B가 솔루션 oracle로 testcase 추가, syntactic validator가 잘못된 input은 Auditor로 환송.

**산출물**:
- `ipe/nodes/auditor.py` — SYSTEM_PROMPT, MIN_ADVERSARIAL_CASES self-loop
- `ipe/nodes/executor.py` (확장) — Phase B + syntactic validator
- `tests/integration/test_phase_b.py`

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P5.1 | auditor.py: prompts + parse_json_array_field 활용 + <8 case self-loop | 3h |
| P5.2 | executor.py: `_validate_input_against_constraints` (variables 범위·형식) | 3h |
| P5.3 | executor.py: Phase B (RTE/TLE 없으면 actual을 expected_output으로 채움) | 2h |
| P5.4 | 통합 테스트 + Phase B 통과 결과로 testcase 누적 검증 | 3h |

**Definition of Done**:
- [ ] `auditor.run(...)` → adversarial_inputs 8~15개 (`{input, category, reason}`)
- [ ] <8개 반환 시 `last_failed_node="auditor"` self-loop
- [ ] Phase B에서 input이 `constraints_structured.variables` 범위 위반 → Auditor 라우팅
- [ ] solution이 RTE/TLE 없으면 testcase에 `kind: "adversarial", expected_output: <actual>` 추가

**테스트**:
- 단위: `_validate_input_against_constraints` (정상/범위초과/타입불일치/형식오류)
- 통합: Phase A 통과 + Phase B 모든 case OK → Phase C로 진행 가능 상태

**핸드오프**: testcase 리스트가 sample + adversarial로 누적. P6에서 generated 추가.

---

### P6 — Generator + Phase C + 병렬화 + 정해 성능 게이트 (2.0일)

**목표**: Codeforces Polygon 패턴으로 시드 스크립트 생성, Phase C는 시드별 stress + 병렬 case 실행 + 정해 50% 성능 게이트.

**산출물**:
- `ipe/nodes/generator.py` — NAME/CATEGORY/DESCRIPTION 파서, _BLOCK_RE
- `ipe/nodes/executor.py` (확장) — Phase C, ThreadPoolExecutor, 정해 성능 게이트
- `tests/integration/test_phase_c.py`

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P6.1 | generator.py: prompts + 정규식 파싱 (3~5 스크립트) | 3h |
| P6.2 | executor.py: `_run_generator` (시드별 invoke) + max_input_bytes cap | 3h |
| P6.3 | executor.py: Phase C 본체 + ThreadPoolExecutor 병렬 case (4 worker) | 4h |
| P6.4 | executor.py: 정해 성능 게이트 (max-stress wall_time ≤ time_limit×0.5) | 2h |
| P6.5 | 통합 테스트: 5 시드 × 3 스크립트 = 15 cases 정상 처리 | 4h |

**Definition of Done**:
- [ ] `generator.run(...)` → 3~5개 generators (`{name, category, code, seeds, description}`)
- [ ] 각 generator 스크립트가 5 시드로 결정론적 output 생성
- [ ] Phase C가 ThreadPoolExecutor로 병렬 실행 (4 worker 기본)
- [ ] generator 스크립트 자체 실패 → Generator 라우팅
- [ ] solution RTE/TLE → Coder 라우팅
- [ ] 정해 wall_time이 time_limit_ms × 0.5 초과 → Coder 라우팅 with "oracle slow" feedback

**테스트**:
- 단위: `_run_generator`, `_parse` (BLOCK_RE)
- 통합: 5개 알고리즘에 대해 P3+P4+P5+P6 cycle 통과율 측정 (목표 ≥ 60%)

**핸드오프**: 3-Phase 검증이 모두 동작. 라우팅은 여전히 단순 (실패 시 halt). P7에서 완성.

---

### P7 — Routing + Retry Budget + iteration_history + Cost Guard (1.5일)

**목표**: graph가 실패 케이스를 적절한 노드로 환송, per-node retry budget 소진 시 halt, 비용 가드 동작.

**산출물**:
- `ipe/graph.py` (확장) — `route_after_executor`, `_halt`, conditional_edges
- `ipe/nodes/*` — 모든 노드 user prompt 끝에 `_build_history_section` 통합
- `tests/integration/test_routing.py`

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P7.1 | graph.py: route_after_executor (cost guard → max_iter → budget → failed node) | 3h |
| P7.2 | graph.py: _halt — final_status 분류 (max_iterations/budget_exhausted/cost_exceeded) | 2h |
| P7.3 | 모든 노드에 _build_history_section 통합 + error_signature 충돌 시 강한 경고 | 3h |
| P7.4 | 통합 테스트: 의도적 실패 사이클 검증 | 4h |

**Definition of Done**:
- [ ] Coder 의도적 무한루프 → TLE → Coder 라우팅 → 다음 시도에 history 첨부
- [ ] coder budget 소진 → `final_status="budget_exhausted"`, halt
- [ ] `--max-cost-usd 0.01` 설정 시 첫 LLM 호출 후 즉시 `cost_exceeded`
- [ ] `--max-iter 1` 설정 시 1 cycle 후 halt
- [ ] 동일 `error_signature` 2회 발생 시 user prompt에 "근본적으로 다른 전략" 강한 경고 삽입

**테스트**:
- 단위: `route_after_executor` (모든 분기), `_build_history_section`
- 통합: mock LLM으로 의도적 실패 패턴 → 라우팅 검증

**핸드오프**: 정상 + 비정상 사이클 모두 안전하게 종료. 산출물 저장과 resume은 P8/P10.

---

### P8 — Checkpointing + Resume + Replay (1.5일)

**목표**: SqliteSaver로 노드 단위 영속화 + `--resume`로 crash 복구 + `--replay`로 LLM 재호출 없이 재현.

**산출물**:
- `ipe/graph.py` (확장) — `build_graph(checkpoint_db=...)` SqliteSaver 통합
- `ipe/observability.py` (확장) — `ReplayTracker.invoke` (trace 캐시 hit)
- `main.py` (확장) — `--resume <run_id>`, `--replay <run_id>`
- `tests/integration/test_resume.py`, `test_replay.py`

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P8.1 | graph.py: SqliteSaver 통합 + thread_id=run_id config | 2h |
| P8.2 | main.py: --resume 핸들링 (runnable.invoke(None, config=...)) | 2h |
| P8.3 | observability.py: ReplayTracker (seq 순서 기반 매칭) | 3h |
| P8.4 | main.py: --replay 핸들링 | 2h |
| P8.5 | 통합 테스트: 의도적 abort + resume + replay 매트릭스 | 3h |

**Definition of Done**:
- [ ] `outputs/<run_id>/checkpoint.db` 자동 생성
- [ ] Phase B 도중 KeyboardInterrupt → `--resume <run_id>` → 같은 super-step부터 재개
- [ ] `--replay <run_id>` → LLM 호출 0회 발생
- [ ] resume + replay 매트릭스 4가지 모드 모두 동작

**테스트**:
- 단위: ReplayTracker.invoke (cache hit/miss)
- 통합: resume + replay 매트릭스

**핸드오프**: 비용 0 디버깅 가능.

---

### P9 — Evaluator + Calibration Anchors (1.0일)

**목표**: Phase C 성공 후 Evaluator가 anchor set을 동봉하여 난이도 측정.

**산출물**:
- `ipe/calibration/__init__.py` — `load_anchors()`
- `ipe/calibration/anchors.json` — 초기 anchor 4~8개 (Bronze5/Silver3/Gold3/Platinum3)
- `ipe/nodes/evaluator.py` — anchor block 동봉
- `ipe/graph.py` (확장) — `executor → evaluator → END`

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P9.1 | calibration/anchors.json 초기 데이터 + load_anchors() | 2h |
| P9.2 | evaluator.py: _build_anchor_block + run | 3h |
| P9.3 | graph.py: executor → evaluator → END 추가 | 1h |
| P9.4 | 통합 테스트: 검증 통과 후 difficulty 정상 측정 | 2h |

**Definition of Done**:
- [ ] `anchors.json` 4~8개 항목 (id, label, summary, factors)
- [ ] `evaluator.run(...)` → difficulty_label, difficulty_reasoning, difficulty_factors, difficulty_calibration_anchors
- [ ] reasoning에 사용된 anchor id 명시 (`"...closest to bj_1753_gold4"`)

**테스트**:
- 단위: `load_anchors` (파일 부재 / JSON 오류)
- 통합: full pipeline → 난이도 라벨 + reasoning 합리성

**핸드오프**: state에 difficulty 필드 채워짐. P10에서 디스크 저장.

---

### P10 — Output Persistence (1.0일)

**목표**: 최종 state를 `outputs/<run_id>/`에 Polygon 스타일로 저장 + `outputs/by-name/<timestamp>_<algo>` symlink.

**산출물**:
- `ipe/io.py` — `save_result`, `_slug`, `_render_problem_md`
- `tests/test_io.py`, `tests/integration/test_save_result.py`

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P10.1 | io.py: save_result + 폴더 구조 + manifest | 3h |
| P10.2 | io.py: _render_problem_md (사람용 markdown 렌더) | 2h |
| P10.3 | io.py: outputs/by-name/<timestamp>_<algo> symlink (충돌 시 skip) | 1h |
| P10.4 | 통합 테스트: 전 사이클 → outputs 검증 | 2h |

**Definition of Done**:
- [ ] `outputs/<run_id>/{problem.json, problem.md, solution.{py,java}, generators/*.py, tests/*.{in,out}, llm_traces/, checkpoint.db}` 모두 생성
- [ ] `outputs/by-name/<timestamp>_<algo>` symlink가 `<run_id>` 가리킴
- [ ] `problem.json`이 SPEC §6 스키마 준수 (jsonschema validator)

**테스트**:
- 단위: `_slug` (한글, 특수문자, 공백)
- 통합: full cycle → 모든 산출물 파일 존재

**핸드오프**: 산출물이 디스크에 영속화. DB 인서트는 외부 시스템이 manifest 읽어서 처리.

---

### P11 — Observability (1.0일)

**목표**: 구조적 로깅, 메트릭 export, (옵션) LangSmith/OTel.

**산출물**:
- `ipe/logging_config.py` — logging dictConfig
- `ipe/observability.py` (확장) — JSON formatter, 메트릭 emitter
- `tests/test_logging.py`

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P11.1 | logging_config.py: JSON formatter + 노드별 logger | 2h |
| P11.2 | observability.py: 메트릭 emitter (ipe.node.latency_ms 등) | 3h |
| P11.3 | (옵션) IPE_LANGSMITH=1 / IPE_OTEL_ENDPOINT 토글 | 2h |
| P11.4 | 테스트 + 메트릭 표준 키 검증 | 1h |

**Definition of Done**:
- [ ] 모든 노드가 `logger.info(..., extra={...})` → JSON 라인으로 stdout
- [ ] `meta.llm_call_summary`가 problem.json에 정확히 기록
- [ ] (옵션) `IPE_LANGSMITH=1` 시 trace export 동작

**테스트**:
- 단위: JSON formatter (멀티라인 메시지)
- 통합: 1 cycle 실행 후 stdout JSON 라인 파싱 가능

**핸드오프**: 운영 환경에서 로그 수집 가능.

---

### P12 — Tests + CLI Polish + CI (2.0일)

**목표**: 테스트 커버리지 80%+, CLI UX 다듬기, GitHub Actions CI.

**산출물**:
- `main.py` — argparse 완성 (모든 플래그)
- `tests/e2e/test_smoke.py` — 5 알고리즘 골든 set
- `.github/workflows/ci.yml` — lint + unit + integration + sandbox selftest matrix
- `Makefile` (확장) — `make ci`, `make selftest-all`
- `README.md` — quickstart, troubleshooting
- `.pre-commit-config.yaml`

**Sub-tasks**:
| # | 작업 | 예상 |
|---|---|---|
| P12.1 | main.py: 모든 CLI 플래그 (--sandbox/--max-cost/--max-iter/--budget-coder/--resume/--replay/--exec-workers/--strict-sandbox/--parallel-fanout) | 3h |
| P12.2 | tests/e2e/test_smoke.py: 5 알고리즘 (Two Sum, BFS, Dijkstra, Segment Tree, DP) | 4h |
| P12.3 | .github/workflows/ci.yml: ubuntu+macos matrix | 3h |
| P12.4 | README.md + Makefile 확장 + pre-commit hooks | 3h |
| P12.5 | 커버리지 80% 도달 (`pytest --cov=ipe`) | 3h |

**Definition of Done**:
- [ ] `make ci` 한 줄로 lint + unit + integration + sandbox selftest 모두 실행
- [ ] `pytest --cov=ipe` 80%+ coverage
- [ ] `gh workflow run ci.yml` 통과
- [ ] e2e 5 알고리즘 중 4개 이상 success
- [ ] README의 quickstart로 새 환경에서 첫 사이클 실행 가능

**테스트**:
- 단위/통합/sandbox 합산 80%+ 커버리지
- e2e: 실제 LLM 호출, manual trigger / nightly

**핸드오프**: 프로덕션 준비 완료.

---

## 2. 파일 책임 매트릭스

| 파일 | 책임 (한 줄) | Line budget | 핵심 함수 | 의존 import | 첫 작성 Phase | 확장 Phase |
|---|---|---|---|---|---|---|
| `pyproject.toml` | 패키지 메타 + entry_points | ≤80 | — | — | P0 | P12 |
| `requirements.txt` | 핵심 의존성 5개 | ≤20 | — | — | P0 | — |
| `Makefile` | install/test/lint/ci/selftest 단축 | ≤80 | — | — | P0 | P12 |
| `Dockerfile` | sandbox baseline image | ≤60 | — | — | P1 | P12 |
| `.env.example` | 환경 변수 템플릿 | ≤30 | — | — | P0 | — |
| `main.py` | CLI 진입점, argparse, graph.invoke | ≤180 | `main`, `_parse_args`, `_setup_run` | `ipe.graph`, `ipe.io`, `ipe.observability` | P4 | P8, P12 |
| `ipe/__init__.py` | 패키지 마커 | 0 | — | — | P0 | — |
| `ipe/state.py` | TypedDict 정의 | ≤140 | (선언만) | `typing` | P0 | P7 |
| `ipe/llm.py` | Claude wrapper + JSON 파서 | ≤220 | `get_chat`, `parse_json_block`, `parse_json_array_field` | `langchain_anthropic`, `re` | P2 | — |
| `ipe/graph.py` | LangGraph 빌더 + 라우터 | ≤200 | `build_graph`, `route_after_executor`, `_halt`, `_budget_remaining`, `_cost_so_far` | `langgraph`, `ipe.nodes`, `ipe.state` | P4 | P7, P8, P9 |
| `ipe/io.py` | save_result + manifest + symlink | ≤280 | `save_result`, `_slug`, `_render_problem_md` | `json`, `pathlib`, `datetime` | P10 | — |
| `ipe/observability.py` | LLMCallTracker + PRICING + 메트릭 | ≤260 | `LLMCallTracker.invoke`, `ReplayTracker.invoke`, `_cost_usd` | `langchain_anthropic`, `logging` | P2 | P8, P11 |
| `ipe/logging_config.py` | logging dictConfig | ≤80 | `setup_logging` | `logging` | P11 | — |
| `ipe/sandbox/__init__.py` | 패키지 마커 | 0 | — | — | P1 | — |
| `ipe/sandbox/runner.py` | ABC + RunSpec/RunResult | ≤140 | `SandboxedRunner.run`, `isolation_self_test` | `abc`, `dataclasses` | P1 | — |
| `ipe/sandbox/rlimit_runner.py` | T3 fallback | ≤200 | `RlimitRunner.run`, `_apply_rlimits` | `resource`, `subprocess` | P1 | — |
| `ipe/sandbox/sandboxexec_runner.py` | T2.5 macOS | ≤220 | `SandboxExecRunner.run`, `_build_profile` | `subprocess`, `platform` | P1 | — |
| `ipe/sandbox/nsjail_runner.py` | T2 Linux | ≤220 | `NsjailRunner.run` | `subprocess`, `tempfile` | P1 (Linux 시) | — |
| `ipe/sandbox/docker_runner.py` | T1 Docker | ≤240 | `DockerRunner.run`, `_build_image` | `subprocess`, `pathlib` | P1 | — |
| `ipe/sandbox/selector.py` | OS-aware tier 선택 | ≤120 | `pick_runner` | `platform`, sandbox 모듈 | P1 | — |
| `ipe/sandbox/__main__.py` | selftest CLI | ≤100 | (script) | `ipe.sandbox.selector` | P1 | — |
| `ipe/calibration/__init__.py` | anchors 로딩 | ≤80 | `load_anchors` | `json`, `pathlib` | P9 | — |
| `ipe/calibration/anchors.json` | reference 샘플 | ≤200 | (data) | — | P9 | — |
| `ipe/nodes/__init__.py` | 패키지 마커 | 0 | — | — | P0 | — |
| `ipe/nodes/architect.py` | 문제 설계 + constraints_structured | ≤380 | `run`, `_validate_constraints_structured`, `_build_history_section` | `ipe.llm`, `ipe.observability`, `jsonschema` | P4 | P7 |
| `ipe/nodes/coder.py` | 골든 솔루션 | ≤270 | `run`, `_parse_response` | `ipe.llm`, `re` | P3 | P7 |
| `ipe/nodes/auditor.py` | adversarial input | ≤300 | `run` | `ipe.llm`, `ipe.observability` | P5 | P7 |
| `ipe/nodes/generator.py` | 시드 스크립트 | ≤300 | `run`, `_parse` | `ipe.llm`, `re` | P6 | P7 |
| `ipe/nodes/executor.py` | 3-Phase 검증 + 병렬 | ≤620 | `run`, `_compile`, `_execute_solution`, `_run_generator`, `_validate_input`, `_run_phase_a/b/c` | `ipe.sandbox`, `concurrent.futures` | P3 | P4, P5, P6, P7 |
| `ipe/nodes/evaluator.py` | 난이도 + anchors | ≤250 | `run`, `_build_anchor_block` | `ipe.llm`, `ipe.calibration` | P9 | — |
| `tests/test_*` | 단위 | 파일당 ≤300 | — | `pytest`, `pytest-mock` | 각 phase | — |
| `tests/integration/test_*` | 통합 | 파일당 ≤400 | — | `pytest`, `pytest-mock` | P3+ | — |
| `tests/sandbox/test_isolation.py` | 격리 시나리오 | ≤300 | — | `pytest` | P1 | — |
| `tests/e2e/test_smoke.py` | 실제 LLM smoke | ≤300 | — | `pytest` | P12 | — |

**총 예상 코드량 (테스트 제외):** ~4,800줄 / 25 모듈. 800줄 초과 파일 0개.

---

## 3. 의존성 그래프 (Critical Path)

```
                                 ┌────────────────┐
                                 │  ipe.state     │ (P0)
                                 └────────┬───────┘
                                          │ (모든 모듈이 import)
              ┌───────────────────────────┼────────────────────────┐
              ▼                           ▼                        ▼
      ┌──────────────┐           ┌──────────────┐         ┌──────────────┐
      │ ipe.sandbox  │ (P1)      │   ipe.llm    │ (P2)    │ ipe.calibration│ (P9)
      │  *_runner.py │           │              │         │  anchors.json │
      │  selector.py │           └──────┬───────┘         └───────┬───────┘
      └──────┬───────┘                  │                         │
             │                  ┌───────┴───────┐                 │
             │                  ▼               ▼                 │
             │          ┌──────────────┐ ┌──────────────┐        │
             │          │ipe.observ.   │ │ipe.nodes.*   │        │
             │          │.py (P2)      │ │ (P3-P9)      │        │
             │          └──────┬───────┘ └──────┬───────┘        │
             │                 │                │                │
             └─────────────────┴────────────────┼────────────────┘
                                                ▼
                                       ┌──────────────┐
                                       │  ipe.graph   │ (P4 골격, P7 본체, P8 checkpoint)
                                       └──────┬───────┘
                                              ▼
                                       ┌──────────────┐
                                       │   ipe.io     │ (P10)
                                       └──────┬───────┘
                                              ▼
                                       ┌──────────────┐
                                       │   main.py    │ (P4 minimal, P8 resume/replay, P12 polish)
                                       └──────────────┘
```

**Critical path** (선형 의존, 17.5일):
`P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 → P9 → P10 → P11 → P12`

**병렬 가능 (2인 페어 시)**:
- P1 ‖ P2 (P0 후, sandbox와 LLM 독립)
- P5 부분 ‖ P6 부분 (P4 후, auditor/generator 독립. 단 executor.py 충돌 주의)
- P11 부분 ‖ P9~P10

2인 페어 예상: ~12일.

---

## 4. 테스트 전략 매트릭스

| Tier | 위치 | 대상 | 실행 빈도 | LLM 비용 | 의존 |
|---|---|---|---|---|---|
| **단위** | `tests/test_*` | parser, normalize, validators, RunSpec/Result, calibration | 매 commit | $0 | — |
| **통합** | `tests/integration/test_*` | graph round-trip, phase별 시나리오 | 매 PR | $0 (mock LLM) | sandbox |
| **격리** | `tests/sandbox/test_isolation.py` | 의도된 위반 차단 | 매 PR (slow marker) | $0 | sandbox |
| **E2E** | `tests/e2e/test_smoke.py` | 5 알고리즘 실제 LLM cycle | nightly / manual | $5~$15 | API key |

**Coverage 목표**: 단위 ≥ 90% (parser/validator), 통합 ≥ 70% (full graph), 합산 ≥ 80%.

**Mock LLM 전략**:
- `pytest-mock`로 `chat.invoke`를 patch
- `tests/fixtures/llm_responses/<phase>/<scenario>.json`에 고정 응답 저장
- `LLMCallTracker.invoke`는 실 호출, `ChatAnthropic.invoke`만 mock

---

## 5. 부트스트랩 가이드 (P0 상세)

### 5.1 `requirements.txt`
```
langgraph>=0.2.0
langchain-anthropic>=0.2.0
anthropic>=0.40.0
python-dotenv>=1.0.0
jsonschema>=4.20.0
pytest>=8.0.0
pytest-mock>=3.12.0
pytest-cov>=4.1.0
ruff>=0.5.0
mypy>=1.10.0
```

### 5.2 `pyproject.toml` (요지)
```toml
[project]
name = "ipe"
version = "0.1.0"
requires-python = ">=3.11"

[project.scripts]
ipe = "main:main"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
strict = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow",
    "e2e: marks tests requiring real LLM (manual trigger)",
]
```

### 5.3 `.env.example`
```
ANTHROPIC_API_KEY=sk-ant-...
IPE_SANDBOX=auto
IPE_MAX_COST_USD=5.0
IPE_LANGSMITH=
IPE_OTEL_ENDPOINT=
```

### 5.4 `Makefile`
```makefile
install:
	pip install -e ".[dev]"

lint:
	ruff check ipe/ tests/
	mypy ipe/

test:
	pytest -v --cov=ipe --cov-report=term

selftest:
	python -m ipe.sandbox --tier auto

selftest-all:
	python -m ipe.sandbox --tier rlimit
	python -m ipe.sandbox --tier sandboxexec || true
	python -m ipe.sandbox --tier docker || true

ci: lint test selftest

run-sample:
	python main.py --algorithm "Two Sum" --language python --max-iter 3
```

### 5.5 `Dockerfile` (sandbox baseline)
```dockerfile
FROM python:3.11-slim

# Java for Solution.java compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
USER nobody:nogroup

# DockerRunner는 이 이미지를 docker run으로 호출 — entrypoint는 동적 cmd
```

### 5.6 `.github/workflows/ci.yml` (요지)
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: make lint
      - run: make test
      - run: make selftest
```

---

## 6. 위험·완화책

| 위험 | 영향 | 완화 |
|---|---|---|
| **LLM API quota / rate limit** | E2E 테스트 비용·시간 | mock 우선, e2e는 nightly만, exponential backoff |
| **macOS sandbox-exec deprecation** | 미래 macOS에서 T2.5 보장 X | T1(Docker) 권장 documentation, deprecation 모니터링 |
| **Java JVM cold start** | Phase B/C 누적 ~5~10초 | 옵션: persistent JVM (P12 polish), nailgun |
| **계산 비용 폭주** | 한 problem이 $10+ | `--max-cost-usd` 강제 + 메트릭 alert |
| **iteration_history oscillation** | 무한 같은 fix 반복 | error_signature 충돌 감지 + 강한 경고 (P7) |
| **sandbox runner 환경 의존성** | 사용자 macOS에 Docker 미설치 | P1.5 selector 자동 fallback + 명확한 경고 |
| **executor.py 비대화** | 620줄 상한 도달 | Phase A/B/C 헬퍼를 `ipe/nodes/_executor_phases.py`로 분리 가능 (P12 리팩토링) |

---

## 7. 다음 라운드 (out of scope)

P0~P12 완료 후 추후 작업:
- Sub-agent 분해 (Story_Agent + Constraint_Agent)
- Special judge 노드
- Brute-force cross-check
- 난이도 ensemble
- 중복/유사문제 detection
- 새 언어 (C++, Rust, Go)
- Cost-aware model routing
- Persistent JVM

이들은 SPEC §8 P2 / ARCH §8 확장 포인트에 등재. 본 로드맵 종료 후 별도 P13+ 라운드로.

---

## 8. planner 에이전트를 위한 메모

본 로드맵을 이용해 sprint를 만들 때:

1. **Phase = Sprint** 1대1 매핑 권장. 한 sprint에 여러 phase 묶지 말 것 (DoD 합쳐져 sprint 종료 판정 모호).
2. **Sub-task = Ticket** 1대1 매핑. 각 sub-task의 예상 시간이 0.5~4h로 ticket 단위에 적합.
3. **DoD 체크박스가 그대로 acceptance criteria** — sprint 리뷰 시 그대로 사용.
4. **테스트는 같은 phase 내에서 작성**. 다음 phase로 미루면 회귀 위험. 단 e2e만 P12에 모음.
5. **2인 이상** 시 §3 의존성 그래프의 병렬 가능 표시(`P1 ‖ P2`, `P5 ‖ P6 부분`) 활용.
6. **블로킹 의존성** — Pn은 P_{n-1}의 DoD 충족 후 시작. 예외: P11은 P9~P10과 부분 병렬.
7. **Phase별 핸드오프 조건**을 sprint review 진입 게이트로 사용.
