# IPE 코드 리뷰 보고서 — P0~P3 구현 현황

> **리뷰어:** Antigravity (code-reviewer + security-reviewer 역할)  
> **대상:** `feat/p3-coder-executor` 브랜치 (HEAD: `96e771c`)  
> **일시:** 2026-05-08  
> **기준:** IMPLEMENTATION_ROADMAP.md (12-Phase), PROJECT_SPEC.md, ARCHITECTURE.md

---

## 1. 진행 상황 요약

### 브랜치 & 커밋 이력

```
main ← PR#1(p2) ← feat/p3-coder-executor (HEAD)
         │
    feat/p1-sandbox (merged to main via p2 merge)
```

| Phase | 상태 | 커밋 수 | 산출물 |
|-------|------|--------|--------|
| **P0 Bootstrap** | ✅ 완료 | (P1에 포함) | pyproject.toml, state.py, Makefile, .env.example |
| **P1 Sandbox** | ✅ 완료 | 8 커밋 | runner.py(ABC), rlimit_runner, sandboxexec_runner, docker_runner, selector, test_isolation |
| **P2 LLM Layer** | ✅ 완료 (PR#1 merged) | 4 커밋 | llm.py, observability.py, test_llm, test_observability |
| **P3 Coder+Executor** | 🔧 진행 중 | 3 커밋 | coder.py, executor.py (Phase A skeleton) |
| P4~P12 | ⬜ 미착수 | — | — |

### 파일 인벤토리 (구현 코드만)

| 파일 | 줄 수 | Phase | 역할 |
|------|------|-------|------|
| `ipe/state.py` | 110 | P0 | ProblemState + 보조 TypedDict 5개 |
| `ipe/sandbox/runner.py` | 78 | P1 | SandboxedRunner ABC + RunSpec/RunResult |
| `ipe/sandbox/rlimit_runner.py` | 160 | P1 | T3 fallback |
| `ipe/sandbox/sandboxexec_runner.py` | 213 | P1 | T2.5 macOS sandbox-exec |
| `ipe/sandbox/docker_runner.py` | 193 | P1 | T1 Docker |
| `ipe/sandbox/selector.py` | 65 | P1 | tier auto-select |
| `ipe/sandbox/__main__.py` | ~50 | P1 | selftest CLI |
| `ipe/llm.py` | 174 | P2 | get_chat + JSON 파서 |
| `ipe/observability.py` | 132 | P2 | LLMCallTracker + PRICING |
| `ipe/nodes/coder.py` | 139 | P3 | Coder 노드 (fence parse + IMPOSSIBLE) |
| `ipe/nodes/executor.py` | 219 | P3 | Executor (Phase A skeleton) |
| **합계** | **~1,533** | | |

### 테스트 인벤토리

| 파일 | 테스트 수 (approx) | Phase |
|------|-------------------|-------|
| `tests/test_state.py` | 5 | P0 |
| `tests/sandbox/test_isolation.py` | ~12 | P1 |
| `tests/test_llm.py` | ~12 | P2 |
| `tests/test_observability.py` | ~10 | P2 |
| `tests/integration/` | **0** (빈 `__init__.py`만) | P3 ❗ |

---

## 2. Phase별 코드 품질 평가

### P0 — Bootstrap ✅

**상태:** 완벽하게 완료.

- `pyproject.toml`: ruff/mypy/pytest 설정 포함. dev dependencies 분리. ✅
- `state.py`: SPEC §2와 1:1 매핑. `total=False`, `FinalStatus` Literal 타입 분리. ✅
- `Makefile`: `install`, `lint`, `test`, `ci`, `selftest`, `clean` 타겟 완비. ✅
- `NodeRetryBudget` docstring에 coder 기본값이 `4`로 갱신됨 (REVIEW Q5 반영). ✅

**지적사항:** 없음.

---

### P1 — Sandbox Foundation ✅

**상태:** 완료. 3-tier + macOS T2.5 추가로 4-tier 체계. 매우 견고.

**강점:**
- `RunSpec`/`RunResult` frozen dataclass → 불변성(Immutability) 원칙 준수. ✅
- `SandboxedRunner` ABC에 `isolation_self_test()` 추상 메서드 포함 → SPEC §7.2 보안 기준 선제 대응. ✅
- `_classify()` 함수가 rc=-9/137 → MLE, truncated → OLE로 분류. 상태값 체계 일관적. ✅
- `selector.py`의 auto fallback 체인이 깔끔 (Docker → sandbox-exec → rlimit + 경고). ✅
- `test_isolation.py`의 `@pytest.mark.slow` + OS별 `skipif` 분리 잘 됨. ✅

**지적사항:**

| # | 심각도 | 파일 | 내용 |
|---|--------|------|------|
| P1-1 | 🟡 | `sandboxexec_runner.py` L39 | `(allow default)` + targeted deny 전략은 적절한 절충. 다만 docstring에 "보안은 약하다"고 명시한 점은 좋으나, **`(allow process-exec)`가 암묵적으로 허용**되어 sandbox 안에서 `curl`이나 `wget` 호출도 가능함 (network deny로 실패하긴 하지만, 바이너리 접근 자체는 가능). |
| P1-2 | 🟢 | `rlimit_runner.py` L79 | `preexec_fn`은 Python 3.12에서 deprecated 경고 발생 가능. 현재 3.11 타겟이므로 당장은 무방하나 향후 `process_group` 등 대체 검토. |
| P1-3 | 🟢 | `docker_runner.py` L57 | `--tmpfs={spec.cwd}:rw,size={spec.memory_limit_mb}m,exec` — workdir 자체를 tmpfs로 마운트하므로 solution 파일을 호스트에서 먼저 쓰고 bind-mount해야 함. 현재 executor.py에서 `_write_source`가 호스트 경로에 쓰는데, Docker에서는 이 파일이 컨테이너에 보이지 않을 수 있음. **P3.4 통합 테스트에서 반드시 Docker tier로 검증 필요.** |

---

### P2 — LLM Layer ✅

**상태:** 완료. PR#1로 main에 merged.

**강점:**
- `parse_json_block`의 3단계 fallback (fence → bare bracket → error) 견고. ✅
- `parse_json_array_field`의 state machine 파서가 truncated JSON을 우아하게 복구. ✅
- `LLMCallTracker.invoke()`가 trace를 자동 저장하고 `state_calls`에 누적. 관심사 분리 우수. ✅
- 테스트에서 `usage_metadata=None` 케이스와 비-BaseMessage 응답 TypeError를 모두 커버. ✅

**지적사항:**

| # | 심각도 | 파일 | 내용 |
|---|--------|------|------|
| P2-1 | 🟡 | `llm.py` L44-53 | `# type: ignore[call-arg]`가 2곳. `ChatAnthropic`의 타입 정의 문제를 우회하는 것인데, mypy strict 모드에서 이걸 남기면 잠재적 타입 버그를 놓칠 수 있음. `cast()` 또는 별도 wrapper type으로 명시적 처리 권장. |
| P2-2 | 🟢 | `observability.py` L125 | `trace_path`를 `str(trace_path)` (절대경로)로 저장함. SPEC §6의 `problem.json`에서는 `outputs/<run>/llm_traces/<seq>.json` (상대경로)을 기대. ARCH §3.12 L1208에서도 `.relative_to()`를 사용. 현재 구현은 절대경로 → 다른 환경으로 포팅 시 trace 경로가 깨질 수 있음. |

---

### P3 — Coder + Executor 최소회로 🔧 진행 중

**상태:** P3.1~P3.3 커밋 완료. **P3.4(통합 테스트) 미착수.**

**강점:**
- `coder.py`: fence 파싱이 "가장 긴 펜스 선택" 전략으로 ARCH §3.6의 설계를 정확히 구현. ✅
- `coder.py` L57: `FEEDBACK_SUFFIX`에 "이전 시도와 다른 접근법을 사용하라" 지시를 포함 (REVIEW W4 oscillation 방지 적용). ✅
- `executor.py`: `_normalize()`가 `\r\n`, trailing whitespace, strip을 모두 처리. 비교 실패의 주된 원인을 선제 차단. ✅
- `executor.py` L164-166: `constraints_structured`에서 problem-specific time/memory limit을 적용하되, fallback을 default 상수로 처리. ✅

**지적사항:**

| # | 심각도 | 파일 | 내용 |
|---|--------|------|------|
| P3-1 | 🔴 | `tests/integration/` | **통합 테스트가 비어 있음.** ROADMAP P3.4에 "hardcoded '두 수의 합'으로 round-trip" 테스트가 DoD로 명시되어 있으나 아직 없음. **P3 Phase가 완료되려면 이것이 반드시 필요.** |
| P3-2 | 🟡 | `executor.py` L80-83 | `_run_cmd()`에서 Python 실행을 `["python3", "solution.py"]`로 하드코딩. 그런데 sandbox 환경(Docker 이미지)에 따라 `python3`가 없고 `python`만 있을 수 있음. `sys.executable` 사용을 고려하되, Docker 내부에서는 의미 없으므로 **sandbox 환경별 cmd 매핑이 P4 이후에 필요.** |
| P3-3 | 🟡 | `executor.py` L133 | `{**state, ...}` 패턴으로 state를 반환하는데, `coder.py` L115-117에서 `state["llm_calls"]`가 없으면 빈 리스트로 초기화함. 이는 **state를 mutate**하는 것 (불변성 위반). LangGraph가 머지하기 전에 state 자체가 변경됨. `state.get("llm_calls", [])`로 새 리스트를 만들어 반환하는 패턴이 더 안전. |
| P3-4 | 🟡 | `coder.py` L87-91 | `tracker` 파라미터가 `None`이면 회계 없이 직접 호출하는 분기가 있음. production path와 test path의 코드 경로가 갈라져서, **실제 production에서만 발생하는 버그를 test에서 못 잡을 위험**. 테스트에서도 mock tracker를 주입하는 방식이 더 안전. |
| P3-5 | 🟢 | `executor.py` L200-206 | P3 단계에서 Phase A만 통과하면 바로 `final_status="success"`를 반환. 향후 P5/P6에서 Phase B/C가 추가될 때 이 부분이 변경될 예정이므로 TODO 주석으로 명시되어 있어 좋음. 다만 **이 상태에서 end-to-end 테스트를 돌리면 Phase B/C 없이 "성공"으로 끝나므로 false positive 주의.** |

---

## 3. 아키텍처 준수도 점검

| SPEC/ARCH 규칙 | 현재 코드 | 준수 |
|---------------|----------|------|
| `ProblemState` total=False | state.py 모든 TypedDict에 적용 | ✅ |
| `FinalStatus` Literal 4종 | state.py L56-61 | ✅ |
| 모델 ID는 `llm.py`에서 SSOT | ARCHITECT/CODER/AUDITOR/GENERATOR/EVALUATOR_MODEL 5개 정의 | ✅ |
| Executor는 SandboxedRunner.run() 경유 | executor.py가 runner를 인자로 받아 사용 | ✅ |
| sandbox tier = `T1`/`T2.5`/`T3` | 각 Runner 클래스에 ClassVar[str] tier 정의 | ✅ |
| LLM 호출 시 비용 추적 | LLMCallTracker 경유 가능, coder.py에서 tracker 주입 | ✅ |
| `{**state, ...}` 반환 패턴 | coder.py, executor.py 모두 사용 | ✅ |
| 에러 시 `feedback_message` + `last_failed_node` 셋 | executor.py의 모든 실패 경로에서 설정 | ✅ |

---

## 4. 테스트 커버리지 평가

| 모듈 | 단위 테스트 | 통합 테스트 | 평가 |
|------|-----------|-----------|------|
| state.py | ✅ 5 tests | — | 충분 |
| sandbox/* | ✅ 12+ tests (tier별) | ✅ isolation selftest | 매우 우수 |
| llm.py | ✅ 12 tests (파서 edge cases) | — | 우수 |
| observability.py | ✅ 10 tests (mock chat) | — | 우수 |
| nodes/coder.py | ❌ 없음 | ❌ 없음 | **미착수** |
| nodes/executor.py | ❌ 없음 | ❌ 없음 | **미착수** |

> ⚠️ **P3 DoD 미달**: coder.py의 `_parse_response` 단위 테스트와 executor.py의 통합 테스트(`test_minimal_circuit.py`)가 ROADMAP에 명시되어 있으나 아직 없음. P3을 완료로 표시하기 전에 반드시 작성 필요.

---

## 5. 코드 품질 메트릭

| 항목 | 상태 | 비고 |
|------|------|------|
| ruff check | ✅ 통과 (커밋 이력에 style fix 포함) | |
| mypy strict | ⚠️ `type: ignore` 2곳 | llm.py L46, L51 |
| 파일당 줄 수 | ✅ 모두 <250줄 | ECC 규칙 <800줄 충족 |
| 함수 크기 | ✅ 모두 <50줄 | ECC 규칙 충족 |
| 네이밍 | ✅ PEP 8 + 일관적 `_private` 컨벤션 | |
| docstring | ✅ 모든 public 함수에 docstring 존재 | |
| 하드코딩 시크릿 | ✅ 없음 (.env 사용) | |

---

## 6. P3 완료를 위한 TODO

ROADMAP P3 DoD 체크리스트 vs 현재 상태:

- [x] hardcoded problem (`A+B`)을 입력 → Coder가 정답 코드 반환
- [x] Java + Python 둘 다 컴파일/실행 성공 (executor 헬퍼 구현됨)
- [x] sample input "1 2" → expected "3" 일치 검증 (Phase A 로직 구현됨)
- [x] 의도적 syntax error → `compile_err` 반환 (executor 로직 있음)
- [ ] **의도적 무한 루프 → TLE 반환** (로직은 있으나 테스트 없음)
- [ ] **`tests/integration/test_minimal_circuit.py`** (빈 `__init__.py`만 존재)
- [ ] **coder.py `_parse_response` 단위 테스트** (fence 우선순위, IMPOSSIBLE 검출)

---

## 7. 총평 & 권장 액션

### 잘된 점
1. **Phase-branch 워크플로우**를 정확히 따르고 있음 (P1→P2→P3, 각 sub-task별 커밋)
2. **Sandbox 4-tier 구현이 매우 견고** — macOS T2.5 추가는 실용적 판단
3. **LLM Layer의 truncation 복구 파서**(`parse_json_array_field`)는 실전에서 높은 가치
4. **코드 스타일 일관성** — ruff/mypy 통과, docstring 완비, 네이밍 일관

### 즉시 해야 할 것 (P3 완료 전)
1. **`tests/integration/test_minimal_circuit.py` 작성** — hardcoded problem으로 Coder→Executor round-trip
2. **`tests/test_coder.py` 작성** — `_parse_response` 단위 테스트 (fence 선택, IMPOSSIBLE 검출)
3. **coder.py L115-117의 state mutation 수정** — `state["llm_calls"] = []` 대신 새 리스트 반환

### P4 진입 전 확인
1. Docker tier에서의 Executor 동작 검증 (파일 bind-mount 문제, P1-3)
2. `observability.py`의 `trace_path` 절대→상대 경로 전환 (P2-2)
