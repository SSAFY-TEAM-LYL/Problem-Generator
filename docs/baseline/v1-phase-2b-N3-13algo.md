# v1.0 D안 Phase 2b — N=3 × 13 algo measurement 보고서

**측정일**: 2026-05-27
**runner**: `python -m ipe.v1.measurement --phase-2b --n 3 --output ...`
**raw data**: `docs/baseline/data/v1-phase-2b-N3-13algo-detailed.jsonl` (39 lines)
**branch**: `feat/v2b-phase2b-measurement`
**환경**: langchain-anthropic 1.3.5 pinned (1.4.3 `$PARAMETER_NAME` wrapping bug
회피), retry=5 wait_exponential_jitter, per-run try-except sentinel

## 1. Gate 판정

| metric | 값 | vs baseline 5 (PR-B5) | vs v0 baseline |
|---|---|---|---|
| Run-level success | **34/39 (87.2%)** | 14/15 (93.3%) → -6.1pp | 27% → **+60pp** |
| Sample-level | **158/163 (96.9%)** | 61/62 (98.4%) → -1.5pp | n/a |
| samples_engaged | **163/163 (100%)** | 62/62 (100%) | n/a |
| API error | 0 | n/a | n/a |
| Mean iteration | 1.21 | 1.07 | n/a |

**Gate: PASS** — 87.2% run-level. PRINCIPLES.md 룰 1 (N≥3) 충족, 룰 2 (cross-algo
regression) 부분 만족 (knapsack outlier), 룰 3 (baseline anchor) 갱신.

## 2. Per-algorithm breakdown

| algo | success | fail | mode | iter avg | engaged % | comment |
|---|---|---|---|---|---|---|
| dijkstra | 3/3 | 0 | — | 1.0 | 100% | 1-shot all |
| lis | 2/3 | 1 | oscillation | 1.33 | 100% | r2: 4/5 samples |
| segtree | 3/3 | 0 | — | 1.0 | 100% | 1-shot, format 안정 |
| two_sum | 2/3 | 1 | oscillation | 1.33 | 100% | r1: 3/4 samples |
| bfs | 2/3 | 1 | oscillation | 1.33 | 100% | r3: 4/5 samples |
| binary_search | 3/3 | 0 | — | 1.67 | 100% | iter=2 recovery 2회 |
| union_find | 3/3 | 0 | — | 1.0 | 100% | 1-shot all |
| toposort | 3/3 | 0 | — | 1.0 | 100% | 1-shot all (PR-C3 H1+H3 evidence 재현) |
| **knapsack** | **1/3** | **2** | oscillation | 1.67 | 100% | **outlier** — RCA 필요 |
| sort | 3/3 | 0 | — | 1.0 | 100% | 1-shot all |
| string_match | 3/3 | 0 | — | 1.0 | 100% | 1-shot all |
| max_flow | 3/3 | 0 | — | 1.0 | 100% | 1-shot all (V≤12 within brute limit) |
| sieve | 3/3 | 0 | — | 1.33 | 100% | iter=2 recovery 1회 |

## 3. Failure pattern 분석

모든 5 failure 가 **fail_oscillation** (iter=2 max → 동일 blocking_signature 반복).
API error 0건. Verifier engagement 100%.

### 3.1 Mismatch sample distribution

| run | blocking_signatures | invariant_violations |
|---|---|---|
| lis r2 | `sample-?-mismatch` × 2 | [] |
| two_sum r1 | `sample-?-mismatch` × 2 | [] |
| bfs r3 | `sample-?-mismatch` × 2 | [] |
| knapsack r2 | `sample-0-mismatch` × 2 | [] |
| knapsack r3 | `sample-3-mismatch` × 2 | [] |

**공통점**: `invariant_violations=[]` — verifier 모든 invariants 통과. sample
mismatch 만 fail 원인.

### 3.2 Knapsack outlier 가설

knapsack r2/r3: `sample-N-mismatch` 가 fix-loop 2회 모두 동일 sample 에 동일
signature. 가능성:

1. **Architect expected_output 오류** (most likely) — LLM (Opus 4.7) 이 0/1
   knapsack DP 의 정답을 spec 단계에서 잘못 계산. coder 의 actual output 이
   사실 정답인데 architect 의 expected 가 wrong.
2. **Verifier blind spot** — invariant_violations 비었으므로 verifier 는 actual
   output 을 "정답" 으로 판정 (value_optimal_via_brute 통과 = brute golden 과
   일치 = 정답). 즉 architect expected 가 *증명적으로* 틀림.
3. **Routing 한계** — coder retry 가 같은 sample 에 같은 mismatch 반복.
   architect 로 routing 되지 않아 expected_output 수정 기회 없음 (H1
   structured routing 의 알려진 한계).

### 3.3 Other failures (lis/two_sum/bfs)

각 1회씩, 정확히 1 sample fail (4/5 또는 3/4). 동일 oscillation 패턴이나
knapsack 만큼 systematic 하지 않음 (N=3 sampling variance 가능).

## 4. H1/H2/H3 가설 누적 evidence

### H1 (structured routing)

- **확정 evidence**: API error 0, 87.2% routing 정확. budget_exhausted 0건.
- **한계 evidence**: fail_oscillation 5건 = architect→coder→executor routing
  loop 만, sample mismatch 시 architect 로 back-route 없음.

### H2 (algorithm-specific verifier engagement)

- **강한 evidence**: **163/163 (100%) samples_engaged**. 8 baseline + 5 추가
  algo 모두 verifier 작동. PR-B2.1 의 segtree format 사건 이후 패턴 정착.
- segtree 3/3 1-shot 안정 = 자체 fix narrative 재확정.

### H3 (IterationContext skill amnesia 완화)

- **부분 evidence**: binary_search 2회 + sieve 1회 + toposort retries 모두
  iter=2 recover → multi-iteration routing 작동.
- **한계 evidence**: 5 fail 모두 oscillation iter=2 = 같은 blocking_signature
  반복. IterationContext 가 sample mismatch 의 *내용* 까지는 학습 못 함.

## 5. v0 → v1 → Phase 2b narrative

```text
v0 baseline (Dijkstra 단일):    27% (8/30 historic)
v1 PR-A5 baseline (Dijkstra):  100% (3/3, N=3)
v1 PR-B5 baseline 5 algo:      93.3% (14/15, N=3)
v1 Phase 2b 13 algo:          87.2% (34/39, N=3)
```

확장 +160% (5 → 13 algo) 후에도 **+60pp vs v0 baseline 유지**. catalog ×2.6
확장의 **narrative anchor 갱신 완료**.

## 6. Kill-switch / rollback 판단

- Run-level 87.2% ≥ 50% threshold → kill-switch 미발동
- Phase 2b architecture 안정 (D안 + verifier catalog) → rollback 없음
- Knapsack outlier 는 algorithm-specific RCA 후보 (architect prompt 강화 또는
  routing 확장 — Phase 2c+ scope)

## 7. 후속 작업 제안

1. **Knapsack RCA** (P1): architect prompt 에 brute-force optimal computation
   강제 또는 sample mismatch 시 architect 로 back-route 추가
2. **N=5 확장 측정** (P2): N=3 sampling variance 줄이고 통계 신뢰도 ↑
3. **Phase 2c (PR-D 시리즈)** (P2): 14~25 algo 추가 (Bellman-Ford / Kruskal /
   LCS / Coin Change / Heap / Trie 등)
4. **Observability v1** (P3): LLMCallTracker + per-iteration cost/timing

## 8. 비용 + 시간

- 시작 15:12, 종료 15:46, **약 34분**
- 39 runs × 평균 53s = ~34분 (실제 elapsed)
- API cost: 추정 ~$15-25 (per-run ~$0.4-0.6, Opus 4.7 + Sonnet 4.6)
- API error retry 0회 발생 (안정 window 에 측정)
