# Root Cause Analysis — v0.1.1 e2e 0/5 Success

> v0.1.1 release 후 실제 LLM e2e 5 case 2 라운드 (Run 1: 5/8/4/2 budget,
> Run 2: 10/10/6/3 budget) 모두 0/5 success. 코어 인프라는 ✅ 작동하지만
> LLM quality 측면에서 production 미달. 본 RCA는 **문서/구조/구현 3축에서**
> 근본 원인을 추적하고 v0.2.0 actionable 개선 plan을 제시한다.
>
> **분석 시점:** main HEAD `7bc80d4` (v0.1.1 + dotenv fix 직전)
> **e2e raw data:** [`docs/backlog/2026-05-10_e2e-quality.md`](../backlog/2026-05-10_e2e-quality.md)

---

## Executive Summary

### Top 3 Root Causes (Critical)

| # | Root Cause | 영향 | Fix 난이도 |
|---|---|---|---|
| **R1** | **Coder가 abstract feedback만 받음** — "phase C: 4 stress cases failed" | Coder가 어떤 입력에서 어떻게 fail인지 모름 → 동일 fix 반복 | 🟢 Easy (1-2h) |
| **R2** | **Single-shot Coder + W4 prompt-only 강제** — 매 cycle 1회 시도, 같은 algorithm family 반복 | oscillation prompt 무시, 본질적 수정 없음 | 🟡 Medium (4-6h) |
| **R3** | **Generator stress N 무제어** — LLM이 N을 자유롭게 정함, 종종 비현실적으로 큰 N | Coder가 IO 최적화 없으면 즉시 TLE/MLE | 🟡 Medium (3-4h) |

### Top 3 Secondary (High)

| # | Root Cause | 영향 | Fix 난이도 |
|---|---|---|---|
| **R4** | **Auditor budget=2 default가 LLM 비결정성 못 흡수** | Run마다 case별 분산 큼 (Two Sum Run 2 부각) | 🟢 Easy (1줄 변경) |
| **R5** | **Brute cross-check 부재** — golden solution이 oracle 자체 | LLM 산출물 자체의 정확성 검증 메커니즘 없음 | 🔴 Hard (8-12h) |
| **R6** | **Cost 측정 정확도 미검증** — 우리 측정 / 실제 ≈ 2.4× (Run 1+2 누적) | guard over-trigger, 운영 평가 왜곡 | 🟡 Medium (2-3h) |

### v0.2.0 권장 priorities

1. **R1 즉시 처리** (최대 ROI) → 다른 모든 문제의 효과가 증폭
2. **R4 즉시 처리** (1줄) → Auditor 분산 흡수
3. **R3 + R6** → R1 효과 검증을 위한 정확한 측정
4. **R2** → R1 후 효과 부족하면 본격 도입
5. **R5** → 장기 (P14+ 후보)

---

## 상세 분석

### R1 — Coder Abstract Feedback (Critical)

#### 현황 (구현 위치)

`ipe/nodes/_executor_phases.py:_run_phase_c` 마지막 분기:

```python
msg = (
    f"phase C: solution failed on {solution_fail_count} stress "
    f"cases (RTE/TLE/MLE)"
)
return {
    **state,
    "feedback_message": msg,
    "last_failed_node": "coder",
}
```

`ipe/nodes/coder.py:USER_TEMPLATE`:

```
## Previous Failure Feedback
{feedback}  ← "phase C: solution failed on 4 stress cases (RTE/TLE/MLE)"

이전 시도와 다른 접근법을 사용하라 (REVIEW W4: oscillation 방지).
```

#### 문제

Coder가 받는 정보:
- ✅ "phase C에서 4개 fail" (count)
- ✅ "RTE/TLE/MLE 중 하나" (status union)
- ❌ **어떤 입력에서?** (stress generator name + seed)
- ❌ **어떤 status인가?** (RTE? TLE? MLE? — fix 방향이 완전 다름)
- ❌ **stderr 메시지?** (예: `IndexError`, `RecursionError`, `MemoryError`)
- ❌ **input excerpt?** (large N? edge case?)

`state["execution_results"]`에는 이 모든 정보가 있지만 **prompt에 전달되지 않음**.

#### 근거 (e2e 결과)

Run 2 / LIS iter 4 → 5 → 8: 시그니처 `f748a6cd` × 2회. Coder는 같은 abstract message ("solution failed on 2 stress cases") 받고 같은 fix 반복. **만약 prompt에 "stress case input N=85000, expected output [...], your output: IndexError at line 42"가 있었다면 다른 fix를 시도했을 것**.

#### 개선 옵션

**Option A (권장 — Easy)**: Phase C 실패 시 feedback에 첫 N개 fail case의 구체 정보 포함:

```python
def _build_failure_feedback(failures: list[dict]) -> str:
    """첫 3개 fail case의 status + stderr excerpt + input N."""
    lines = [f"phase C: solution failed on {len(failures)} stress cases"]
    for f in failures[:3]:
        gen = f.get("generator", "?")
        seed = f.get("seed", "?")
        st = f.get("status", "?")
        stderr_excerpt = (f.get("stderr") or "")[:200]
        inp_bytes = f.get("input_bytes", 0)
        lines.append(
            f"  - generator={gen} seed={seed} status={st} "
            f"input_bytes={inp_bytes} stderr={stderr_excerpt!r}"
        )
    return "\n".join(lines)
```

**Option B (Strong)**: `state["last_failed_inputs"]: list[dict]` 신규 필드 추가, Coder prompt가 별도 섹션으로 표시. abstract message는 기존 유지.

**Option C (Maximal)**: 한 fail 입력의 stdin 전체 + 정해 expected_output을 Coder에게 전달. token 비용 ↑ but 가장 강력한 fix 시그널.

#### 권장 implementation

1. `_executor_phases.py:_run_phase_c`: failure list 보존 (이미 result dict에 있음)
2. `_run_phase_c` 라우팅 시 feedback_message를 Option A 형식으로 빌드
3. Phase B도 동일 — `_run_phase_b`도 abstract message만 보낸다

**예상 effort**: 1-2h. **예상 효과**: Coder fix 시도의 구체성 ↑ → oscillation 감소.

---

### R2 — Single-shot Coder + W4 Prompt-only (Critical)

#### 현황

- 매 cycle Coder 1회 LLM call (one-shot)
- W4 oscillation 감지 시 prompt에 "DIFFERENT STRATEGY REQUIRED" 추가
- **prompt에 의존하는 강제 — LLM이 무시 가능**

#### 문제 (e2e 결과)

Run 2:
- LIS: 시그니처 `f748a6cd` 2회 / `178582d4` 2회 → 4번 반복 fix 모두 동일 패턴
- BFS: 시그니처 `178582d4` × 2회 + `e03dad60` × 1회 → fix 노력에도 같은 algorithm family

W4 prompt가 효과적이지 않은 이유:
1. LLM이 이전 시도의 algorithmic core를 prompt history에서 보지 못함 (코드 자체는 user message 안 들어감, feedback만)
2. `temperature=0.7` 고정 — LLM이 같은 distribution에서 sampling
3. "switch to a fundamentally different strategy" 지시가 추상적 — 구체적인 algorithm 옵션 제시 X

#### 개선 옵션

**Option A (Coder fanout)**:
- 한 cycle에 N=3 다른 솔루션 동시 생성 (`temperature=0.3, 0.7, 1.0`)
- Executor가 sample testcase에서 모두 검증
- 가장 fail count 적은 솔루션 선택
- **비용**: ×3 token cost per cycle. but cycle 횟수 감소로 net 효과

**Option B (Self-critique loop)**:
- Coder 본인이 작성 → 자체 review (system prompt에 "review your code for edge cases" 추가) → 수정
- 한 LLM call에 chain-of-thought로 처리
- **비용**: token ↑ but call 수 동일

**Option C (W4 → Architect 라우팅)**:
- 시그니처 3회+ 발견 시 `_decision`에서 `architect`로 라우팅 (문제 자체 재설계)
- prompt 강제 대신 graph routing으로 강제
- Architect의 새 문제 → Coder 새 시도

**권장**: **Option A + Option C 결합**. Option A는 cycle 효율 ↑, Option C는 escape hatch.

#### 권장 implementation

1. `ipe/graph.py:_route_after_decision`: oscillation 감지 추가 (history에서 same_sig × 3+ 검색) → "architect" 라우팅
2. `ipe/nodes/coder.py`: `--coder-fanout N` 인자 받아 N개 솔루션 동시 생성, executor가 best 선택. (architect/auditor/generator는 single-shot 유지)

**예상 effort**: 4-6h. **예상 효과**: oscillation 빠른 escape + Coder 다양성.

---

### R3 — Generator Stress N 무제어 (Critical)

#### 현황

`ipe/nodes/generator.py`:
- LLM이 자유롭게 generator 스크립트 작성
- `category`: RANDOM_SMALL / RANDOM_MEDIUM / MAX_STRESS / SPECIAL_STRUCTURE
- N range는 LLM 판단 — `constraints_structured.variables.max` 기준이지만 강제 X

#### 문제 (e2e 결과)

- Two Sum Run 1: stress case 1-2개 fail (N=대값에서 솔루션이 IndexError)
- LIS Run 1: 5/5 generator script 실패 — LLM이 입력 형식 오작성

**N gradient 부재** — 작은 N → 큰 N 점진 검증 불가:
- 작은 N에서 정해 output 검증 (정확성)
- 중간 N에서 timeout 검증 (성능)
- 큰 N에서 memory 검증 (확장성)

현재는 generator 5개 모두 비슷한 large N → Coder가 어디서 어떻게 fail인지 진단 어려움.

#### 개선 옵션

**Option A (Generator prompt 강화)**:
- system prompt에 명시: "RANDOM_SMALL: N ≤ n_max/100, MAX_STRESS: N = n_max"
- 카테고리별 N range 강제

**Option B (Generator 카테고리 default 설정)**:
- ROADMAP §4.4 카테고리별 N 기본값 명시
- `_run_generator` 안에서 category에 따라 자동 N 조정

**Option C (DP/그래프 등 알고리즘별 입력 형식 가이드)**:
- LIS 같은 시퀀스 입력은 RANDOM_SMALL부터
- 그래프 알고리즘은 SPECIAL_STRUCTURE (path, complete graph) 우선

**권장**: **A + B 결합**. system prompt 강화로 즉시 효과 + executor 측에서 fallback 강제.

#### 권장 implementation

1. `ipe/nodes/generator.py:SYSTEM_PROMPT`: 카테고리별 N range 명시 강화
2. `ipe/nodes/_executor_helpers.py:_run_generator`: category가 RANDOM_SMALL인데 N>1000이면 warn (또는 N cap)
3. Generator 카테고리별 1개 이상 강제 (현재는 자유) — `_parse`에서 검증

**예상 effort**: 3-4h.

---

### R4 — Auditor Budget Default 2 (High)

#### 현황

`main.py` default: `--budget-auditor 2`. Run 1+2 모두 default 2 사용 (Run 2도 안 늘림).

#### 문제

Auditor는 8 valid adversarial 생성을 시도 — LLM 비결정성으로 일부 case에서 syntactic validator fail (constraints 위반 input).

Two Sum Run 2:
- iter 1: `no adversarial_inputs` (정상 첫 진입)
- iter 2: `phase B: 4 adversarial inputs violate constraints` ← LLM 실수
- → Auditor budget 2 소진 → halt

**Auditor LLM 1번 실수만으로 case 전체가 fail**.

#### 개선 옵션

**Option A (Default 4)**: `--budget-auditor 4`. 분산 흡수 ↑.

**Option B (Auditor 자체 self-validation)**: Auditor가 출력 후 본인 출력을 syntactic validator에 통과시키도록 prompt 강화 (chain-of-thought).

**권장**: A 즉시 (1줄), B는 R1 fix 후 잔존 시.

#### 권장 implementation

`main.py:_parse_args`: `--budget-auditor` default `2` → `4`.

**예상 effort**: 1줄. **예상 효과**: case별 분산 직접 감소.

---

### R5 — Brute Cross-check 부재 (High)

#### 현황

ROADMAP §7 (Future) — Coder가 golden + brute 둘 다 작성, executor가 비교.

현재 `solution_code`는 single golden — oracle이 자기 자신.

#### 문제

LLM이 만든 솔루션 자체가 잘못되어 있어도 (예: edge case 누락), 솔루션 출력이 oracle. → Phase C에서 정해의 출력이 잘못되어도 발견 못 함.

#### 개선 옵션

**Option A**: Coder가 small-N brute (O(N²) 같은 무식한 구현)을 함께 작성. Executor Phase C에서 stress 입력의 부분집합 (small N case)에서 golden vs brute 비교.

- golden ≠ brute → golden 또는 brute 잘못 → 둘 다 다시
- golden = brute → 정확성 confidence ↑

**Option B (간단 버전)**: golden만 sample N개 더 stress test. Phase B의 expected_output 자체를 cross-check.

**권장**: A (장기) — v0.2.0 후반 또는 v0.3.0.

**예상 effort**: 8-12h (Coder 노드 출력 schema 변경 + Phase C 비교 로직).

---

### R6 — Cost 측정 정확도 (Medium)

#### 현황

- 우리 측정 (Run 1+2): $4.84
- Anthropic console (사용자 보고, Run 2 마지막 시점): $1.98
- 비율: 2.4×

#### 가능한 원인

| 가설 | 가능성 | 검증 방법 |
|---|---|---|
| **PRICING table stale** | 🟡 중간 | Anthropic 가격 페이지 vs `ipe/observability.py:PRICING` 비교 |
| **Tier 할인** | 🟢 높음 | 사용자 계정 monthly volume tier 확인 |
| **Anthropic auto prompt caching** | 🔴 낮음 | `usage_metadata`에 cache 필드 노출되지만 우리가 무시 (확인됨: 노출 안 됨) |
| **input_tokens 정의 차이** | 🟡 중간 | LangChain ChatAnthropic vs Anthropic SDK raw response 비교 |

#### 권장 implementation

1. **단기**: `PRICING` table에 주석 추가 — "List price 기준, Tier 할인 미반영"
2. **중기**: `_cost_usd`에 `cache_creation_input_tokens`, `cache_read_input_tokens` 처리 (langchain expose 시):
   ```python
   def _cost_usd(model, in_tok, out_tok, *, cache_creation=0, cache_read=0):
       p = PRICING[model]
       cost = (
           (in_tok - cache_creation - cache_read) * p["input"]
           + cache_creation * p["input"] * 1.25
           + cache_read * p["input"] * 0.1
           + out_tok * p["output"]
       ) / 1_000_000
   ```
3. **검증 e2e**: Anthropic console과 우리 측정 case별 비교 → 차이 분포 확인

**예상 effort**: 2-3h.

---

## 추가 발견 (Lower Priority)

### R7 — Temperature 고정 (Low)

`ipe/llm.py`: Coder만 `temperature=0.7`. 다른 노드는 default (0.0?). oscillation 감지 시 temperature 동적 조정 메커니즘 없음.

**개선**: oscillation 감지 시 next call의 temperature 0.7 → 1.0 boost.

### R8 — Phase B / Phase C feedback 통일 (Low)

Phase B / Phase C 둘 다 R1과 동일 abstract feedback 문제. R1 fix가 양쪽 모두 cover.

### R9 — Generator 카테고리 강제 부재 (Low)

`generator.py:_parse`는 category 검증 안 함. LLM이 모두 RANDOM_SMALL로 만들어도 통과. R3에서 함께 처리.

---

## v0.2.0 Sprint Plan (제안)

### Sprint 1 — High-ROI Fixes (1.5일)

| 작업 | Effort | 근거 |
|---|---|---|
| R1: Coder feedback 구체화 | 1-2h | 모든 다른 R 효과의 prerequisite |
| R4: auditor_budget default 4 | 0.5h | 1줄 변경 |
| R6 단기: PRICING 주석 + 검증 e2e | 2-3h | 운영 평가 정확성 |
| 검증 e2e (5 case + Anthropic 비교) | 30min + $5 | 효과 측정 |

**예상 효과**: 0/5 → 2-3/5 success (R1만으로 의미있는 개선 기대)

### Sprint 2 — Coder 다양성 (2일)

| 작업 | Effort |
|---|---|
| R2 Option C: W4 → architect 라우팅 (시그니처 3회+) | 2h |
| R3 Generator N gradient + 카테고리 강제 | 3-4h |
| R7 Temperature dynamic | 1-2h |
| 검증 e2e (5 case) | 30min + $5 |

**예상 효과**: 3-4/5 success (DoD 충족 가능)

### Sprint 3 — Robust Coder (3-5일, 옵션)

| 작업 | Effort |
|---|---|
| R2 Option A: Coder fanout (N-shot) | 4-6h |
| R5: Brute cross-check (P14+) | 8-12h |
| R6 중기: cache 토큰 처리 | 2-3h |

**예상 효과**: 4-5/5 success 안정 (production-ready 수준)

---

## 위험 + 완화

| 위험 | 가능성 | 영향 | 완화 |
|---|---|---|---|
| R1 fix가 token 비용 큰 폭 ↑ | 🟡 중간 | $5/case → $7-8 | feedback excerpt 길이 cap (200 chars/case × 3 cases) |
| R2 fanout이 cost guard 빠르게 trigger | 🟡 중간 | budget 자주 소진 | `--coder-fanout` opt-in (default 1) |
| Run마다 결과 분산 (LLM 비결정성) | 🟢 높음 | 검증 데이터 노이즈 | 각 case 3 run × seed → 평균 |
| Coder 모델 escalation 불가 (이미 Opus) | 🔴 확정 | model 측 한계 | prompt engineering / sub-agent 분해로 우회 |

---

## 결론 + 다음 행동

### 즉시 (이번 주)
1. **R1 + R4**를 한 PR로 처리 (~3-4h, 실제 LLM e2e 검증 포함)
2. e2e 5 case 재실행 (R1 fix 후) → 효과 측정
3. 결과를 본 RCA 부록 섹션에 추가 기록

### 다음 주 (조건부)
- R1 fix가 4-5/5 도달 → DoD 충족 → v0.2.0 release
- R1 fix가 2-3/5 → Sprint 2 (R2/R3/R7) 진행
- R1 fix가 0-1/5 → 본 RCA 재검토 (다른 root cause 가능성)

### 장기 (v0.3.0+)
- R5 Brute cross-check
- Multi-language oracle (Python + C++ 검증)
- Sub-agent 분해 (Algorithm + Implementation)

본 RCA는 **운영 가능 상태로 가는 가장 짧은 경로**를 우선시한다. 가장 큰 ROI는 R1 (Coder feedback 구체화) — 이것 하나로 다른 R 효과가 증폭된다.

---

## 부록 A — Sprint 1 (R1 + R4 + R6 단기) e2e Run 3 결과

> commit `0d12d5f` (`feat/v0.2.0-sprint-1-r1-r4`) — 5 case e2e 재실행. 10분 10초.
> R1 (detailed feedback) + R4 (auditor budget 4) + R6 (PRICING 주석) 적용 후.

### 결과 매트릭스 (Run 3)

| Case | Run 1 | Run 2 | **Run 3 (Sprint 1)** | 변화 |
|---|---|---|---|---|
| Two Sum | budget_exhausted | budget_exhausted | **max_iterations** | 🟡 더 멀리 감 (R4 효과) |
| BFS | budget_exhausted | budget_exhausted | budget_exhausted | — |
| Dijkstra | max_iterations | budget_exhausted | budget_exhausted | — |
| Segment Tree | budget_exhausted | budget_exhausted | budget_exhausted | — |
| LIS | budget_exhausted (Generator fail) | budget_exhausted | budget_exhausted | — |
| **Success** | **0/5** | **0/5** | **0/5** | **DoD 미충족** |

### R1 fix 검증 — Coder prompt에 실제로 detail 전달됨

Two Sum iter 6 trace (`0008_coder.json`) 확인:

```
phase C: solution failed on 2 stress cases (RTE/TLE/MLE)

Failing cases (first 2):
  1. phase=stress status=RTE elapsed_ms=22
     generator=gen_max_stress_no_resonance seed=2 input_bytes=1977874
     input: '200000 -2000000000\n926756583 911666163 60721576 98338421 ...'
  2. phase=stress status=RTE elapsed_ms=25
     generator=gen_max_stress_no_resonance seed=3 input_bytes=1977546
     input: '200000 -2000000000\n255512576 636343333 584361683 ...'
```

Auditor 분기도 정상:
```
[iter 2] auditor: phase B: 1 adversarial inputs violate constraints
  Violating adversarial inputs (first 1):
    1. reason='input value 4000000000 above max 2000000000'
       input: '2 4000000000'
```

**→ R1 fix 의도대로 작동**. abstract `"phase C: 2 cases failed"` 대신 status / elapsed_ms / generator / seed / input_bytes / input excerpt가 prompt에 정확히 노출됨.

### 그럼에도 0/5 — 추가 root cause 발견

#### R10 (NEW) — Generator stress N이 비현실적

Two Sum: N=200000 + value range `[-2,000,000,000, 2,000,000,000]` → **input 약 2MB**. 정상 hash 솔루션이 IO 처리 미흡 시 즉시 RTE. R3 (Generator stress N 제어) 시급도 ↑↑.

이는 RCA 본문 R3의 가설("Generator가 LLM 자유롭게 N 정함")을 **e2e raw input으로 확정**:
- ROADMAP §4.4의 카테고리별 N 가이드는 prompt 수준에서만 — LLM 무시
- `_run_generator`나 generator validator가 N cap 미적용

#### R11 (NEW) — Coder detailed feedback 봐도 fix 못 함

Two Sum iter 4 → 5 → 6 → 7+ : `4 cases failed` → `4 cases` → `2 cases` → ... 점진 감소하나 max_iter 안에 0 도달 못 함. **R1만으로는 cycle 효율 ↑이지만 cycle 횟수 한계** (현재 max_iter=8).

가설:
- Coder LLM이 IO 최적화 (`sys.stdin.buffer.read`, BufferedReader)를 자체적으로 못 떠올림
- Generator의 input excerpt 200 chars만 보고는 "전체 size 2MB"의 의미를 추론 못 함 (input_bytes 값 보여줘도)

→ **R1 후속 보강** (Sprint 1.5):
- input_bytes ≥ 1MB 시 prompt에 명시 경고: "**HIGH-VOLUME INPUT** — use buffered IO"
- Coder system prompt에 IO 최적화 패턴 명시 강화

### 비용 측정

- 우리 측정 (Run 3): TBD (실행 직후 전체 토큰 합계 미집계, 추후 산출)
- Anthropic console (실측): 사용자 확인 필요
- R6 단기 주석 적용으로 PRICING이 upper bound임 명시됨

### Sprint 1 결론

| 항목 | 평가 |
|---|---|
| R1 — detailed feedback 작동 | ✅ 의도대로 prompt에 전달 |
| R4 — auditor budget 4 효과 | 🟡 부분 (Two Sum이 처음 max_iterations 도달) |
| R6 단기 — PRICING 주석 | ✅ 문서화 완료 |
| **DoD 5/5 중 4+ success** | 🔴 **미충족 (0/5)** |
| 다음 단계 | **Sprint 1.5 + Sprint 2** (R10/R11 신규 + R2 W4→architect + R3 Generator N) |

### 다음 PR 권고

1. **Sprint 1 PR 머지** — R1/R4/R6 단기 안정 (해 안 끼침, infra 개선)
2. **Sprint 1.5 (작은 추가 PR)**:
   - R10 Quick: `_run_generator`에 input_bytes cap (예: 500KB) — LLM이 비현실적 N 생성 시 자동 reject + retry
   - R11 Quick: Coder system prompt에 IO 최적화 명시 + feedback의 input_bytes ≥ 1MB 시 `HIGH-VOLUME INPUT` 경고
3. **Sprint 2** — R2 architect 라우팅 + R3 본격 + R7 temperature
