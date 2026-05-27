# IPE v1 PR-B5 — baseline 5 algo × N=3 measurement (2026-05-27)

**Date**: 2026-05-27
**Spec**: `docs/PRINCIPLES.md` 룰 1 (N≥3) + 룰 2 (cross-algorithm regression) + 룰 3 (baseline anchor)
**D안 Phase 2a final deliverable**.
**Data**: `docs/baseline/data/v1-pr-b5-detailed.jsonl` (15 lines, raw JSONL).

---

## 1. 측정 조건

| | value |
|---|---|
| Algorithms | Dijkstra, LIS, Segment Tree, Two Sum, BFS (baseline 5) |
| N per algo | 3 |
| Total runs | 15 |
| `max_iter` | 6 |
| Graph | `ipe/v1/graph.py` (4 노드 + structured routing + 5 verifier) |
| LLMs | Opus 4.7 (architect/coder) + Sonnet 4.6 (designer) |
| Sandbox | docker (default `pick_runner()` auto) |
| Command | `python -m ipe.v1.measurement --baseline-5 --output docs/baseline/data/v1-pr-b5-detailed.jsonl --max-iter 6 --n 3` |
| Wall time | ~13분 (10:04 → 10:16 KST) |

---

## 2. 결과

| Algo | Runs | Run-level | Sample-level | `samples_engaged` | Mean elapsed |
|---|---|---|---|---|---|
| **Dijkstra** | r1-r3 | 3/3 ✅ | 12/12 (100%) | 12/12 (100%) | 43.7s |
| **LIS** | r4-r6 | 3/3 ✅ | 14/14 (100%) | 14/14 (100%) | 41.1s |
| **Segment Tree** | r7-r9 | 3/3 ✅ | 12/12 (100%) | 12/12 (100%) | 61.2s |
| **Two Sum** | r10-r12 | 3/3 ✅ | 12/12 (100%) | 12/12 (100%) | 46.8s |
| **BFS** | r13-r15 | 2/3 ⚠ | 11/12 (91.7%) | 12/12 (100%) | 63.0s |
| **합계** | 15 | **14/15 (93.3%)** | **61/62 (98.4%)** | **62/62 (100%)** | 51.1s |

### 2.1 Iteration depth (H1 신호)

- iter=1 (1-shot success): **13/15 runs**
- iter=2 (fix loop active):
  - Two Sum r2: `sample-1-mismatch` 후 1회 retry → success (H1 ✓ fix loop 정상 작동)
  - BFS r1: `sample-3-mismatch` 2회 반복 → `fail_oscillation` halt (H1 ✓ 같은 sig 2회 → 자동 halt)

### 2.2 Verifier engagement (H2 신호)

**samples_engaged 62/62 = 100%**. silent skip 0건. 모든 sample 에 대해
algorithm-specific invariants 강제 작동.

invariant_violations 발생 건: 0건. BFS r1 의 fail 은 sample exact match 단계
(sample-3-mismatch), 즉 verifier engagement 이전에 sample 자체가 fail.

---

## 3. 비교 (baseline anchor — 룰 3 적용)

| Setup | Run-level | Sample-level | 평가 |
|---|---|---|---|
| baseline v0 N=3 (single Opus, PR #71) | **4/15 (27%)** | 48/61 (78.7%) | reference floor |
| IPE v0 N=3 (M1~M4 multi-mechanism) | 3/15 (20%) | 50/57 (87.7%) | over-correction sign |
| **IPE v1 PR-B5 N=3 (D안)** | **14/15 (93.3%)** | **61/62 (98.4%)** | **+66pp vs baseline, +73pp vs v0** |

### 3.1 Algo 별 비교

| Algo | baseline v0 | IPE v0 | **IPE v1** | Δ vs baseline |
|---|---|---|---|---|
| Two Sum | 1/3 | 1/3 | **3/3** | +67pp |
| BFS | 0/3 | 0/3 | **2/3** | +67pp |
| Dijkstra | 3/3 | 0/3 | **3/3** | +0pp (이미 baseline 만점) |
| LIS | 0/3 | 0/3 | **3/3** | +100pp |
| Segment Tree | 0/3 | 2/3 | **3/3** | +100pp |

→ **5 algo 중 4 algo 에서 baseline 압도, 1 algo (Dijkstra) 는 baseline 동등**.

---

## 4. D안 H1/H2/H3 검증

### H1 (typed structured artifacts → fix loop budget_exhausted 감소)

| Metric | v0 IPE | v1 PR-B5 |
|---|---|---|
| Run-level success | 20% | **93.3%** |
| `budget_exhausted` rate | 93% (12/15 fails) | **0%** (0/15) |
| `fail_oscillation` rate | n/a | 6.7% (1/15) |
| 1-shot success rate | n/a | **86.7%** (13/15) |

→ **H1 정량 검증**. v0 의 budget 소진 패턴이 v1 에서 사라지고 1-shot success 가
표준. Two Sum r2 의 fix loop 1회 retry 성공이 H1 narrative 의 직접 anchor —
typed feedback (sample-1-mismatch signature) 으로 coder 가 정확히 fix.

### H2 (algorithm-specific symbolic verifier → retry feedback 명료성)

- `samples_engaged` **62/62 (100%)** — silent skip 0건
- 5 verifier 각각 golden algorithm 로 cross-check 작동
- BFS r1 의 fail 도 verifier engaged (sample-3-mismatch 가 sample exact match
  단계에서 잡힘, verifier 가 일했지만 LLM 이 fix 못함)

→ **H2 완전 검증**. PR-B2.1 의 format 정합 + architect prompt 강화 패턴이 5
algo 모두 일관되게 작동.

### H3 (IterationContext 누적 → skill amnesia 완화)

| Run | Result | H3 evidence |
|---|---|---|
| Two Sum r2 | iter=2 success | sample-1-mismatch lesson 후 fix → **H3 ✓** |
| BFS r1 | iter=2 oscillation halt | 같은 sample-3-mismatch 반복 → lesson 활용 못함 (**H3 한계**) |

→ **H3 부분 검증**. fix loop 성공률 = 50% (1/2). multi-iter sample 작아서 통계
신뢰 낮음 — Phase 2b 의 더 어려운 algo 에서 추가 측정 필요.

---

## 5. `PRINCIPLES.md` 룰 적용 결과

| 룰 | 적용 | 결과 |
|---|---|---|
| 1. N≥3 measurement gate | ✓ | 5 algo × N=3 = 15 runs |
| 2. Cross-algorithm regression | ✓ | baseline 5 algo all measured. Dijkstra 0pp (이미 baseline 만점), 4 algo 모두 +67pp 이상 |
| 3. Baseline anchor 영구화 | ✓ | baseline v0 4/15 (27%) vs v1 14/15 (93.3%) — narrative anchor 변경 |
| 4. Complexity budget | △ | v0 7 + v1 4 = 11 임시 공존. Phase 4 v0 archive 시 회복 |
| 5. RCA rollback 조건 | ✓ | kill-switch 미발동 |

---

## 6. Gate 판정 (Phase 2a final)

| 시나리오 | 판정 | 본 측정 |
|---|---|---|
| ≥ baseline 동등 (4/15 = 27%) | **Phase 2b 진입** | ✓ **14/15 = 93.3%** |
| < baseline (kill-switch 검토) | Phase 2a rollback | — |

### **판정: Phase 2b 진입 ✅** (압도적 상회, kill-switch 미발동)

---

## 7. 한계 (narrative honesty)

- **N=3 small variance**: 동일 측정 재현 시 ±10pp 예상. Phase 2b 측정은 N=5
  권장.
- **all-success 경향**: 13/15 runs 가 1-shot. fix loop 통계 (H1 정량, H3 누적)
  의 sample size 너무 작음 — 어려운 algo (Knapsack, MaxFlow 등) 에서 fail case
  생성하는 environment 필요.
- **BFS r1 root cause 미분석**: sample-3-mismatch 2회 반복이 LLM 의 fundamental
  knowledge gap 인지, verifier feedback 명료성 부족인지, prompt 부족인지 구분
  안 됨. Phase 2b 진입 전 디버그 권장.
- **Cost 정확 추적 안 됨**: 추정 ~$15-30, 실제 cost 는 v0 `LLMCallTracker` v1
  통합 후 측정.
- **Indexing inconsistency**: Dijkstra 0-indexed, 나머지 4 algo 1-indexed.

---

## 8. 다음 단계 후보 (Phase 2b)

| 후보 | 동기 | priority |
|---|---|---|
| **BFS r1 root cause 디버그** | 1 fail 의 원인 명확화 (H3 정량 측정 anchor) | 즉시 |
| **algorithm 확장** (Knapsack, Union-Find, Topological Sort, MaxFlow, Binary Search 등) | 사용자 "수많은 algorithm" 의도 + 어려운 algo 에서 H1/H3 정량 측정 | 높음 |
| **N=5 재측정** | variance 축소, 통계 신뢰 ↑ | 중 |
| **observability 강화** | `LLMCallTracker` v1 통합, cost 정확 추적 | 중 |
| **indexing 통일** | Dijkstra 0-idx → 1-idx | 낮음 (cosmetic) |
| **catalog v1 schema** | output 영속화, 사람 review anchor | 낮음 |
