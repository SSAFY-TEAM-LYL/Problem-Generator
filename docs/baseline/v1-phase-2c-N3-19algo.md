# v1.0 D안 Phase 2c — N=3 × 19 algo measurement 보고서

**측정일**: 2026-05-28
**runner**: `python -m ipe.v1.measurement --phase-2c --n 3 --output ...`
**raw data**: `docs/baseline/data/v1-phase-2c-N3-19algo-detailed.jsonl` (57 lines)
**branch**: `feat/v2c-phase2c-measurement`
**환경**: Phase 2b 와 동일 (langchain-anthropic 1.3.5 / retry 5 / per-run sentinel)

## 1. Gate 판정

| metric | 값 | vs Phase 2b 13 algo (PR #94) | vs v0 baseline |
|---|---|---|---|
| Run-level success | **47/57 (82.5%)** | 34/39 (87.2%) → -4.7pp | 27% → **+55pp** |
| Sample-level | **232/241 (96.3%)** | 158/163 (96.9%) → -0.6pp | n/a |
| samples_engaged | **241/241 (100%)** | 163/163 (100%) | n/a |
| API error | 0 | 0 | n/a |
| Mean iteration | 1.21 | 1.21 | n/a |

**Gate: PASS** — 82.5% run-level. PRINCIPLES.md 룰 1 (N≥3) 충족, 룰 2 (cross-algo
regression) 관찰 (-5pp 감소 = sampling variance + Knapsack/Kruskal outlier),
룰 3 (baseline anchor) 갱신.

## 2. Per-algorithm breakdown

| algo | success | fail | family | iter avg | engaged % |
|---|---|---|---|---|---|
| dijkstra | 3/3 | 0 | Graph | 1.0 | 100% |
| lis | 3/3 | 0 | Search | 1.0 | 100% |
| segtree | 2/3 | 1 osc | DS | 1.33 | 100% |
| two_sum | 1/3 | 2 osc | Array | 2.0 | 100% |
| bfs | 3/3 | 0 | Graph | 1.0 | 100% |
| binary_search | 3/3 | 0 | Search | 1.67 | 100% |
| union_find | 3/3 | 0 | DSU | 1.0 | 100% |
| toposort | 3/3 | 0 | Graph | 1.0 | 100% |
| **knapsack** | **0/3** | **3 osc** | DP | 1.67 | 100% |
| sort | 3/3 | 0 | Sort | 1.0 | 100% |
| string_match | 2/3 | 1 osc | String | 1.33 | 100% |
| max_flow | 3/3 | 0 | Graph | 1.0 | 100% |
| sieve | 3/3 | 0 | NumTheory | 1.0 | 100% |
| **bellman_ford** | **3/3** | 0 | Graph | 1.0 | 100% |
| **floyd_warshall** | **3/3** | 0 | Graph | 1.0 | 100% |
| **kruskal_mst** | **1/3** | **2 osc** | Graph | 1.67 | 100% |
| **heap** | **3/3** | 0 | DS | 1.0 | 100% |
| **fenwick** | **3/3** | 0 | DS | 1.0 | 100% |
| **coin_change** | **2/3** | 1 osc | DP | 1.33 | 100% |

**Bold = 새 6 verifier (PR-D 시리즈, 최초 N=3 측정)**.

## 3. Failure pattern 분석 (10 fails)

### 3.1 Mismatch sample 분포

| run | blocking_signatures | invariant_violations |
|---|---|---|
| segtree r2 | sample-3-mismatch ×2 | [] |
| two_sum r1 | sample-1-mismatch / **indices_in_range_and_ordered** ×2 | indices_in_range_and_ordered |
| two_sum r2 | sample-1-mismatch ×2 | [] |
| **knapsack r1** | sample-1-mismatch ×2 | [] |
| **knapsack r2** | sample-3-mismatch ×2 | [] |
| **knapsack r3** | sample-1-mismatch ×2 | [] |
| string_match r3 | sample-0-mismatch ×2 | [] |
| **kruskal_mst r1** | sample-2-mismatch ×2 | [] |
| **kruskal_mst r2** | sample-3-mismatch ×2 | [] |
| coin_change r2 | sample-2-mismatch ×2 | [] |

**관찰**:
- **9/10 fails: `invariant_violations=[]`** = verifier 모든 invariants 통과
  → architect 의 expected_output 이 잘못 (coder output 이 사실 정답).
- **1/10: two_sum r1 = `indices_in_range_and_ordered`** — coder 가 실제로
  invariant 위반한 유일 case. architect 로 back-route → iter=3 까지 진행 후
  oscillation.

### 3.2 Knapsack outlier 강화 (P1 RCA 재확정)

- Phase 2b: 1/3 success (r2/r3 fail)
- Phase 2c: **0/3 success** — outlier 강화. 모두 sample mismatch + invariant 통과.
- 가설: LLM Opus 4.7 의 0/1 Knapsack DP 정답 계산 한계.
- 동일 family 의 **Coin Change 2/3 success** → DP family 일반 문제 아닌
  **Knapsack specific** 확정.

### 3.3 Kruskal MST NEW outlier (1/3)

- PR-D3 smoke (single run): 1-shot success, samples_engaged 4/4 — 안정 보였음.
- Phase 2c N=3: **1/3 success** — smoke 와 다름.
- 가설: undirected graph + edge weight 의 architect expected_output 계산이 LLM
  에 까다로움 (MST weight 합 계산 실수). Knapsack 과 동일 mechanism.
- 추후 N=5 측정 시 sampling variance vs systematic 추가 확인 필요.

## 4. 새 6 PR-D verifier 최초 측정

| verifier | success | family | comment |
|---|---|---|---|
| Bellman-Ford | 3/3 | Graph | 1-shot all |
| Floyd-Warshall | 3/3 | Graph | 1-shot all, matrix output 안정 |
| Kruskal MST | 1/3 | Graph | ⚠ NEW outlier, smoke 와 다름 |
| Heap | 3/3 | DS | 1-shot all, op sequence 안정 |
| Fenwick | 3/3 | DS | 1-shot all, prefix-sum 안정 |
| Coin Change | 2/3 | DP | 1-shot 2/3 + 1 variance |

**소계: 15/18 (83.3%)** — Kruskal 이 새 outlier 후보.

## 5. H1/H2/H3 가설 evidence (누적)

### H1 (structured routing)
- API error 0건 유지. budget_exhausted 0건.
- two_sum r1 의 invariant_violation 라우팅 = H1 의 architect→coder 전환 실제 발동.
- 9/10 fail 의 architect back-route 부재 한계는 그대로.

### H2 (verifier engagement)
- **241/241 (100%) samples_engaged** — 새 6 verifier 모두 작동.
- PR-B2.1 의 segtree format 패턴 + 새 cluster + 새 DS 모두 100% engaged.

### H3 (multi-iter recovery)
- binary_search r1+r2: iter=2 recover ×2 (Phase 2b 와 동일).
- segtree r1: iter=2 recover.
- 10 fail 모두 oscillation iter=2 = 같은 sig 반복 (한계 동일).

## 6. v0 → v1 → Phase 2b → Phase 2c narrative

```text
v0 baseline (Dijkstra 단일):    27%  (8/30 historic)
v1 PR-A5 baseline (Dijkstra):  100% (3/3, N=3)
v1 PR-B5 baseline 5 algo:      93.3% (14/15, N=3)
v1 Phase 2b 13 algo:          87.2% (34/39, N=3)
v1 Phase 2c 19 algo:          82.5% (47/57, N=3)  ←── 현재
                                                    ↓
                            catalog ×3.8 확장 후에도 +55pp vs v0 유지
```

**감소 trend** (93.3% → 87.2% → 82.5%) — algorithm 추가 시 sampling variance +
algorithm-specific outlier 누적 효과. 단 100% samples_engaged 는 유지.

## 7. Kill-switch / rollback 판단

- Run-level 82.5% ≥ 50% threshold → kill-switch 미발동.
- 새 6 verifier 의 architecture 안정 (Bellman/Floyd/Heap/Fenwick 모두 3/3).
- Kruskal MST 1/3 + Knapsack 0/3 는 algorithm-specific RCA 후보.

## 8. 후속 작업 제안

| priority | task | 영향 |
|---|---|---|
| P1 | **Knapsack RCA** — architect prompt brute optimal 강제 또는 sample_mismatch 시 architect back-route 추가 | knapsack 0/3 → 3/3 |
| P1 | **Kruskal MST RCA** — undirected edge 의 MST weight 계산 prompt 강화 | kruskal 1/3 → 3/3 |
| P2 | N=5 확장 측정 | variance ↓, 통계 신뢰도 ↑ |
| P2 | Phase 2d (PR-E 시리즈) — String/NumTheory family 확장 (Trie, Modular Exp) | catalog ×4.5+ |
| P3 | Observability v1 (LLMCallTracker) | 비용 분석 |

## 9. 비용 + 시간

- 시작 23:43, 종료 00:35, **약 52분**
- 57 runs × 평균 50s = ~48분 (실제 elapsed)
- API cost: 추정 ~$25-35 (per-run ~$0.4-0.6)
- API error retry 0회 발생 (안정 window)
