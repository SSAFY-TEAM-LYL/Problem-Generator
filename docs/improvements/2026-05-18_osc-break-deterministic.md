# R-osc-break — Phase A Oscillation Breaker (결정적 차단)

**Date**: 2026-05-18 (Round 11)
**Scope**: v0.2.1 결정적 fix sprint — 첫 번째 P0 항목
**Related**: CHANGES.md §16.1, REQUIREMENTS.md §5.3 (알려진 한계),
`docs/improvements/2026-05-14_sandbox-infra-rca.md` §D.5

---

## 1. 문제 정의

### 1.1 관찰된 증상

Round 10 (Sprint 4) 종료 시점 e2e 매트릭스 (Run 9~12):

| Case | Run 9 | Run 10 | Run 11 | Run 12 | 안정성 |
|---|---|---|---|---|---|
| Topological Sort | OK | OK | OK | OK | 4/4 |
| **BFS** | FAIL | OK | FAIL | OK | **2/4** |
| Dijkstra | OK | OK | OK | OK | 4/4 |
| LIS | OK | OK | OK | OK | 4/4 |
| Segment Tree | FAIL | FAIL | FAIL | FAIL | 0/4 (R-gen-cap 대상) |

BFS variance 2/4 — fail 시 trace 공통 패턴:

```
iter 1: architect → ... → executor → fail (feedback X)
        decision: architect retry, budget 2→1
iter 2: architect → ... → executor → fail (feedback X, same signature)
        decision: architect retry, budget 1→0
iter 3: architect → ... → executor → fail (feedback X)
        decision: architect budget=0 → budget_exhausted → END
```

architect가 같은 실패 signature로 architecture를 반복 생성. budget 소진 후 종료.

### 1.2 기존 메커니즘이 막지 못한 이유

Sprint 1~4 의 R 시리즈 중 W4 / R1 / R11이 oscillation 방지를 시도:

| 메커니즘 | 방식 | 한계 |
|---|---|---|
| W4 prompt 강제 | "이전과 다른 접근으로" 텍스트 삽입 | LLM이 같은 패턴 재생성 (텍스트 가이드 무시) |
| `build_history_section` | history + "DIFFERENT STRATEGY REQUIRED" 경고 | 동일. prompt-only는 LLM 응답 변동성 통제 못 함 |
| R13 lessons_learned | Coder가 매 cycle 1-line LESSON 누적 | Coder 한정. Architect oscillation 무관 |

**근본 한계**: prompt-side fix는 LLM의 응답 분포를 좁힐 뿐, **반복 응답을
거부하지는 못한다**. 결정적 차단은 라우팅 레벨에서만 가능.

---

## 2. 해법 — `_detect_architect_oscillation` + `_decision` swap

### 2.1 감지 함수 (`ipe.graph._detect_architect_oscillation`)

```python
def _detect_architect_oscillation(state, current_signature) -> bool:
    if state.get("last_failed_node") != "architect":
        return False
    if not current_signature:
        return False
    history = state.get("iteration_history") or []
    prior = sum(
        1 for r in history
        if r.get("node") == "architect"
        and r.get("error_signature") == current_signature
    )
    return prior >= 1  # 이번 cycle 포함 = 2회+
```

조건 셋 다 만족해야 True:
1. 현 cycle이 architect 실패
2. signature 비공백 (`""` signature는 의미 없음)
3. history에 동일 (architect, signature) 1회+ — 이번 포함 2회+

### 2.2 `_decision`의 swap

```python
osc_break = _detect_architect_oscillation(state, current_sig)
origin_node = failed  # = "architect"
if osc_break:
    failed = "coder"  # routing/budget 전환 대상만 swap
# budget 차감: budget["coder"] -= 1
# history record: node=origin_node("architect"), action="oscillation_break"
```

- **swap 대상**: routing target과 budget 차감 대상만 — coder로
- **원인 노드 보존**: history record의 `node`는 architect 그대로 (디버깅용 trace
  정확성 유지)
- **action 마킹**: `"retry"` → `"oscillation_break"` — replay/분석 시 발동 시점
  명확히 식별

### 2.3 발동 후 흐름

```
iter 1: architect fail (sig X) → history += (architect, X, retry), budget arch 2→1
iter 2: architect fail (sig X, 동일) → 감지! swap → failed="coder"
        history += (architect, X, oscillation_break), budget coder 4→3
        route_after_decision → "coder"
iter 3: coder retry → ...
```

architect는 무한 retry에서 벗어나고, coder가 동일 problem 위에서 다른 솔루션
시도. 만약 coder budget도 0이면 정상 `budget_exhausted(coder)` 종료.

---

## 3. 우선순위 설계 결정

`_decision`의 halt 가드 순서:

1. cost guard (`cost_exceeded`)
2. success preserve
3. max_iter (`max_iterations`)
4. **R-osc-break 감지 + swap** ← 신규
5. budget exhausted (swap된 failed 기준)
6. budget 차감
7. history append (swap된 라우팅 + 원인 노드 분리 기록)

oscillation 감지는 halt 가드(1~3) 다음, budget 체크(5) **이전**:
- cost/iter/success는 항상 우선 (시스템 안전)
- swap 결과로 coder budget 0이면 `budget_exhausted(coder)`로 정상 종료
  (architect budget은 보존되므로 v0.2.1 후속 PR에서 다시 활용 가능)

---

## 4. 테스트 (+11)

`tests/test_routing_units.py`:

### `TestDetectArchitectOscillation` (6 cases)
- 빈 history → False
- failed != "architect" → False
- 빈 signature → False
- 다른 signature → False
- 같은 architect signature 1회 (이번 포함 2회+) → True
- coder 노드의 같은 signature → False (architect 한정)

### `TestDecisionOscillationBreaker` (5 cases)
- 첫 architect 실패 (history 비어있음) → swap 없음, architect budget 차감
- 같은 signature 2회 → swap to coder, coder budget 차감, history action="oscillation_break"
- swap 후 `_route_after_decision` → "coder"
- swap + coder budget 0 → `budget_exhausted(coder)`
- 다른 signature → swap 없음 (정상 architect retry)

전체 회귀: **266 passed + 3 skipped** (v0.2.0의 247 + 본 PR 신규 +11 + 기존 누락분).

---

## 5. 한계 + 후속

- **BFS e2e 실측**: 결정적 unit 검증으로 동작 보장. 실제 5회 run 측정은 v0.2.1
  release 검증 시점 (LLM 호출 비용/시간).
- **R-gen-cap (Segment Tree)**: 별도 PR로 분리. 검증 범위 분리해 회귀 원인
  추적 용이.
- **architect → auditor / generator oscillation**: 본 fix는 architect 한정.
  auditor/generator의 반복 retry는 별도 검토 필요 (현 BFS/ST 사례에는
  unrelated).
- **swap 후 problem 자체가 잘못된 경우**: coder가 잘못된 문제 위에서 시도 →
  실패할 가능성 존재. 그러나 architect budget을 보존하므로 다음 cycle에서
  architect 재진입 가능 (`_decision`의 라우팅은 매 cycle 새로운 `last_failed_node`
  기준).
