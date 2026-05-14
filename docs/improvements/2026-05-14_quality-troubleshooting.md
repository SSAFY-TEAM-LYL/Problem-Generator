# Quality Troubleshooting Playbook — Sprint 3 진입 전

> v0.2.0 Sprint 1/1.5/2 (R1 / R4 / R6 / R11 / R10 + max_iter=10) 적용 후
> e2e success rate 0/5 → 1/5 도달. Sprint 3 진입 (R13 Reflexion → R15 Brute
> oracle → R14 Best-of-N) 전, 본 playbook은:
> 1. 현재 quality baseline 정량화
> 2. 알고리즘별 LLM 실패 패턴 카탈로그
> 3. LLM trace 분석 가이드
> 4. 각 R 도입 효과 측정 protocol
> 5. Troubleshooting flow
>
> **참조**: [RCA](2026-05-10_root-cause-analysis.md) · [e2e backlog](../backlog/2026-05-10_e2e-quality.md)

---

## 0. 본 문서 사용 시점

| 상황 | 어느 섹션 참조 |
|---|---|
| e2e 결과 분석 시작 | §1 baseline → §2 패턴 매칭 |
| 0/5 또는 1/5 success | §5.1 troubleshooting flow |
| 새 R 도입 후 측정 | §4 protocol |
| Coder가 같은 fix 반복 | §3 trace 분석 → oscillation 식별 |
| hang / 비정상 종료 | §5.2 hang flow |
| 비용 예측 / 초과 분석 | §1.3 cost baseline + R6 PRICING 주석 |

---

## 1. 현재 e2e Baseline (Run 1~6-retry)

### 1.1 Final Status 매트릭스

| Case | Run 1 | Run 2 | Run 3 (S1) | Run 4 (S1.5) | Run 5 (max_iter=10) | Run 6-retry (R10) |
|---|---|---|---|---|---|---|
| Two Sum | budget_exh | budget_exh | max_iter | max_iter | budget_exh | budget_exh |
| BFS | budget_exh | budget_exh | budget_exh | budget_exh | **success** | budget_exh |
| Dijkstra | max_iter | budget_exh | budget_exh | max_iter | budget_exh | max_iter |
| Segment Tree | budget_exh | budget_exh | budget_exh | max_iter | budget_exh | budget_exh |
| LIS | budget_exh | budget_exh | budget_exh | budget_exh | budget_exh | **success** |
| **Success** | 0/5 | 0/5 | 0/5 | 0/5 | **1/5** | **1/5** |
| 소요 | 11분 19초 | 8분 59초 | 10분 10초 | 10분 47초 | 8분 27초 | 9분 41초 |

### 1.2 Case별 부분 Success Rate (n=2, Run 5 + Run 6-retry 평균)

> 같은 코드 baseline (R1+R10+R11+max_iter=10) 두 run 평균.

| Case | success | max_iter | budget_exh | rate |
|---|---|---|---|---|
| Two Sum | 0 | 0 | 2 | 0/2 = 0% |
| BFS | 1 | 0 | 1 | 1/2 = 50% |
| Dijkstra | 0 | 1 | 1 | 0/2 = 0% |
| Segment Tree | 0 | 0 | 2 | 0/2 = 0% |
| LIS | 1 | 0 | 1 | 1/2 = 50% |
| **전체** | **2/10** | 1/10 | 7/10 | **20%** |

**해석**:
- 5 case 중 평균 1개 success — **확률적으로 5/5 일관성 미달**
- BFS / LIS만 success 도달 — 둘 다 단순 알고리즘 + 작은 입력
- Two Sum / Dijkstra / Segment Tree — IO 또는 자료구조 복잡성으로 budget_exh

### 1.3 Cost / Token Baseline

| 출처 | Run 1+2+3 누적 | 비고 |
|---|---|---|
| 우리 측정 (`ipe.observability.PRICING`) | ~$7-8 | list price, Tier 미반영 |
| Anthropic console 실제 청구 | ~$3 | Tier 할인 + cache 적용 |
| 비율 | **2.4× over-measure** | R6 주석에 명시됨 |

Run 평균 LLM call 수: 30-40 (case당 6-10 calls).

### 1.4 알려진 비결정성 출처

| 출처 | 영향 | 완화 |
|---|---|---|
| LLM temperature (Coder 0.7, 나머지 default) | 같은 prompt에 다른 코드 | R7 (temp dynamic), R14 (Best-of-N) |
| Architect storytelling 변형 (같은 알고리즘에 다른 narrative) | case별 stress pattern 다름 | R2 (architect 라우팅) |
| Generator script — N / value range / 분포 | stress 강도 case마다 다름 | R3 (N gradient), R10 (size cap) ✅ |
| Auditor adversarial 분포 | constraint violator 비율 변동 | R4 (budget 4) ✅ |

---

## 2. 알고리즘별 LLM 실패 패턴 카탈로그

### 2.1 Two Sum (해시 + IO)

**관찰 패턴 (Run 1~6)**:
- N=200000 + value range ±2B → input 1.6-1.97MB (R10 적용 후 < 2MB)
- Coder 솔루션이 `input()` 기반이면 즉시 TLE
- R11 적용 후 buffered IO 사용 시도 — 그러나 8 iter 안에 정확성 + IO 둘 다 못 잡음

**대표 fail signature** (Run 3 trace `0008_coder.json`):
```
status=RTE elapsed_ms=22
generator=gen_max_stress_no_resonance seed=2
input_bytes=1977874
```

**예상 R13 / R15 효과**:
- R13 (Reflexion): "이전에 `input()`을 buffered로 안 바꿔서 RTE 났다" 학습 누적 → 다음 cycle 빠르게 fix
- R15 (Brute oracle): brute solution O(N²) hash 미사용 → small N에선 golden과 일치 → 정확성 확정

### 2.2 BFS shortest path

**관찰 패턴**:
- Run 5에서 첫 success 도달 — 알고리즘 자체는 비교적 단순
- 다른 run에서 fail은 stress case의 큰 그래프에서 메모리/timeout

**대표 fail signature** (Run 2 history):
```
phase C: solution failed on 4 stress cases (RTE/TLE/MLE)
```

**예상 R13 / R14 효과**:
- BFS는 algorithm family 분기점 적어 R13 효과 중간
- R14 (Best-of-3) — 그 중 1개라도 IO 최적화 + recursion limit 모두 갖춘 솔루션이면 success

### 2.3 Dijkstra single-source shortest path

**관찰 패턴**:
- priority queue 구현 변동 — `heapq` 사용 / 직접 구현 / array 기반
- recursion 사용 시 1500+ depth에서 stack overflow
- Run 6-retry에서 max_iterations 도달 (Coder가 끝까지 시도) — fix 시도 활발

**대표 fail signature**:
- 큰 그래프에서 priority queue 부재 → O(VE) → TLE

**예상 R 효과**:
- R13: "지난번 array-based 구현해서 TLE 났다" 학습 → heapq 우선 시도
- R15 brute: brute Dijkstra (O(V²)) cross-check — golden heapq와 비교

### 2.4 Segment Tree range sum

**관찰 패턴**:
- Coder가 segment tree 구현 자체는 정상이나 **lazy propagation** 누락 빈번
- update + query mixed query에서 stress fail
- Run 4에서 max_iterations 도달 — fix 시도하나 lazy 안 떠올림

**대표 fail signature**:
- update + query mix에서 RTE 또는 WA (검증 가능 oracle 부재)

**예상 R 효과**:
- R15 (Brute oracle)가 **결정적** — brute `O(N)` per query 와 segment tree `O(log N)` 비교 시 lazy 누락 즉시 발견

### 2.5 LIS (Longest Increasing Subsequence)

**관찰 패턴**:
- Generator script 자체 실패 (Run 1) — DP 입력 형식 변동 (1줄 / 다줄 / 공백 구분 등)
- O(N²) vs O(N log N) 선택 — N=10^5에서 O(N²)는 TLE
- Run 6-retry에서 첫 success — R10 효과로 generator 안정

**예상 R 효과**:
- R3 (Generator N gradient): RANDOM_SMALL / MAX_STRESS 카테고리별 N 명시 → script 안정
- R13: "O(N²) 시도해서 TLE 났다" 학습

---

## 3. LLM Trace 분석 가이드

### 3.1 Trace 파일 위치

운영:
```
outputs/<run_id>/llm_traces/<seq>_<node>.json
```

e2e (pytest tmp_path):
```
/private/var/folders/.../pytest-of-iseungmin/pytest-<N>/test_e2e_full_cycle_<algo>_<idx>/<run_id>/llm_traces/
```

### 3.2 Trace 파일 구조

```json
{
  "seq": 5,
  "node": "coder",
  "model": "claude-opus-4-7",
  "messages": [
    {"role": "system", "content": "You are The Coder ..."},
    {"role": "user", "content": "## Problem\n\n... ## Previous Failure Feedback\n..."}
  ],
  "response": {"content": "..."},
  "usage": {"input_tokens": ..., "output_tokens": ...},
  "duration_ms": ...,
  "cost_usd": ...
}
```

### 3.3 진단 패턴

#### A. Coder가 detailed feedback 받았는지 확인 (R1 검증)

`messages[1].content`에서 `"Previous Failure Feedback"` 섹션 찾아:
- ❌ `"phase C: solution failed on 4 stress cases (RTE/TLE/MLE)"` 만 있음 → R1 미적용
- ✅ `"Failing cases (first 3): 1. phase=stress status=RTE ..."` 포함 → R1 작동

#### B. high-volume warning 발화 (R11 검증)

같은 섹션에서:
- ✅ `"⚠️  HIGH-VOLUME INPUT detected (max X.XX MB)"` 발견 → R11 작동
- ❌ 1MB 미만 input이거나 첫 cycle → 미발화 (정상)

#### C. W4 oscillation 감지 (history 분석)

`messages[1].content`의 `## Previous Attempts` 섹션:
```
[iter 3] coder (f16cb8e1): phase C: solution failed on 4 stress cases
[iter 5] coder (f16cb8e1): phase C: solution failed on 4 stress cases  ← 같은 signature
[iter 6] coder (f16cb8e1): phase C: ...                                ← 3회+ — Sprint 2 후 architect 라우팅 대상
```

→ R2 (W4→architect) 가 적용되면 3회+ 시 architect 노드로 라우팅됨.

#### D. Coder LLM 응답 자체 분석

`response.content`에서 솔루션 추출 (펜스 블록) — IO 패턴 확인:
- ✅ `sys.stdin.buffer.read().split()` — R11 권고 따름
- ❌ `for _ in range(N): input()` — TLE 위험
- ✅ `from heapq import heappush, heappop` — Dijkstra 정상
- ❌ recursion without `sys.setrecursionlimit` — stack overflow 위험

### 3.4 Cost 분석

```bash
# 전체 cost 합산
jq -s 'map(.cost_usd) | add' llm_traces/*.json

# 노드별 평균
jq -s 'group_by(.node) | map({node: .[0].node, avg_cost: (map(.cost_usd) | add / length)})' llm_traces/*.json
```

---

## 4. Sprint 3 각 R 도입 효과 측정 Protocol

### 4.1 R13 (Reflexion) 측정

**가설**: 매 fail 후 Coder가 "왜 fail 했는지" 1-2 문장 작성하여 history에 누적 → oscillation 감소.

**측정 지표**:
| 지표 | 방법 | baseline (Run 6-retry) | R13 후 기대 |
|---|---|---|---|
| Oscillation rate | 동일 error_signature × 2+ 횟수 / 총 cycle | TBD (trace 분석) | -30% |
| Cycle 횟수 평균 | iter 도달 평균 | 6.8 (Run 6-retry) | -1 |
| Success rate | n=3 평균 | 1/5 | 1.5-2/5 |
| Token cost | run당 합계 | $2-3 | +10% (reflection prompt) |

**검증 e2e**: Run 7 (R13만 적용) × 3회 (n=3 reliability).

### 4.2 R15 (Brute Oracle Cross-check) 측정

**가설**: Coder가 golden + brute 작성 → Phase C에서 small N stress 시 두 출력 비교 → 정확성 deterministic 확정.

**측정 지표**:
| 지표 | 방법 | 기대 |
|---|---|---|
| golden ≠ brute 발견 | Phase C log | 첫 검증에서 case당 1-2회 발견 가능 |
| oracle 자체 오류 발견 | golden=brute일 때 둘 다 expected와 다른 경우 | 0회 목표 |
| 추가 token cost | brute 작성 + 추가 stress 실행 | +20-30% |
| Success rate | n=3 | 2-3/5 |

**검증**: R13 → R15 순서로 적용, R13 baseline 대비 ΔR15 계산.

### 4.3 R14 (Coder Best-of-N) 측정

**가설**: 한 cycle에 N=3 솔루션 동시 생성 (temperature 0.3/0.7/1.0) → sample/adversarial fail count 최소 채택.

**측정 지표**:
| 지표 | 방법 | 기대 |
|---|---|---|
| Best 솔루션의 fail count | N=1 baseline 대비 평균 ↓ | -40% |
| Token cost | 3× LLM call | +180% (단, cycle 수 -50% 기대) |
| Success rate | n=3 | 3-4/5 |
| Net cost | token × cycle 수 | -10 ~ +20% |

**리스크**: 3 솔루션이 모두 같은 oversight 가지면 효과 0 — 다양성 확보를 위해 temperature spread 필수.

### 4.4 측정 비교 표

| Sprint | 적용 | n=3 평균 success | 누적 비용 |
|---|---|---|---|
| baseline (현재) | R1+R4+R6+R10+R11+max_iter=10 | 1/5 | $2.50/run |
| Sprint 3 step 1 | + R13 | 1.5-2/5 | $2.75 |
| Sprint 3 step 2 | + R15 | 2-3/5 | $3.30 |
| Sprint 3 step 3 | + R14 | 3-4/5 | $5-6 |

각 step 후 본 표에 실측 채워 비교.

---

## 5. Troubleshooting Flow

### 5.1 e2e 결과 0/5 → 진단 절차

```
1. trace 파일 위치 확인 → 어떤 case의 어떤 iter에서 stuck?
   ↓
2. 마지막 final_status 확인
   ├─ budget_exhausted → 어떤 node budget? (last_failed_node 확인)
   │    ↓
   │    architect → R2 라우팅 대상
   │    coder    → R13/R14 대상
   │    auditor  → R4 budget 더 ↑ (default 4 이미 적용)
   │    generator→ R3 / R10 cap 확인
   ├─ max_iterations → R14 fanout 또는 max_iter 추가 ↑
   └─ cost_exceeded → max_cost_usd 또는 R6 PRICING 재확인
   ↓
3. Coder prompt에 detail / warning 발화 확인 (§3.3 A/B)
   ├─ ❌ 미발화 → R1/R11 적용 안 됨, regression 가능성
   └─ ✅ 정상 → LLM quality 한계 → Sprint 3 진입
   ↓
4. W4 oscillation 확인 (§3.3 C)
   ├─ 동일 signature × 3+ → R2 (architect routing) 적용 필요
   └─ signature 다양 → fix 시도 활발, R13/R14 적용 후 재측정
```

### 5.2 hang / 비정상 종료 → 진단

```
1. process 살아있는지 확인
   ps aux | grep pytest
   ↓
2. 마지막 trace timestamp 확인
   ls -la <run_dir>/llm_traces/ | tail -1
   ↓
3. 5분 이상 변동 없음 → Anthropic API hang
   ├─ kill pytest, 부분 결과 분석
   └─ R12 (timeout + retry) 우선순위 ↑ (RCA에 등재 필요)
   ↓
4. 정상 진행 중 → 단순히 LLM 응답 대기
   다음 case 까지 평균 2-3분 대기
```

### 5.3 일관되게 같은 case fail → 알고리즘 family 변경

```
1. Architect storytelling 변형이 너무 좁은 algorithm family로 유도?
   → 다른 시도에서 architect가 다른 변형 만들도록 강제 (R2)
   ↓
2. Generator stress 패턴이 한 종류만 dominant?
   → R3 (카테고리 강제)로 분포 다양화
   ↓
3. Coder가 같은 algorithm family 반복?
   → R14 (Best-of-N) temperature spread로 다양성 강제
   → 또는 R13 (Reflexion)으로 "다른 알고리즘 family 시도" 학습
```

---

## 6. Sprint 3 진입 체크리스트

R13 PR 시작 전:

- [ ] 본 playbook 머지 (baseline + protocol 명시)
- [ ] RCA 문서에 R12 (hang resilience) backlog 등재
- [ ] Run 7-baseline 측정 (현 코드 n=3) — Sprint 3 비교 대상
- [ ] (선택) Anthropic console 비용 확인 — R6 측정 정확도

R13 PR 본격:

- [ ] `ipe/nodes/coder.py`: response 후 self-reflection LLM call 추가 (또는 chain-of-thought)
- [ ] `ipe/state.py`: `lessons_learned: list[str]` 필드 추가
- [ ] `build_history_section`: lessons를 prompt에 누적 노출
- [ ] 단위 테스트 + e2e Run 7-R13 측정

각 step 후 본 playbook §4.4 표 실측 채우기.

---

## 부록 A — 알려진 한계

- **5/5 일관성**: LLM 비결정성으로 100% 도달 어려움. 4-5/5 평균이 현실적 목표
- **Anthropic 의존**: 외부 API hang / rate limit 시 e2e 전체 lose (R12 우선순위 ↑)
- **모델 escalation 불가**: 이미 Opus 4.7 사용 — model 측 한계는 prompt engineering / sub-agent로만 우회
- **Cost 측정**: list price 기준 upper bound (실제 청구 / 우리 측정 ≈ 0.4 ratio)

본 playbook은 **Sprint 3 진입 baseline**이다. Sprint 3 완료 후 측정 결과를 부록 B로 추가하여 실효 검증한다.
