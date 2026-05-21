# Wider analysis — IPE N=3 deeper insights (Wider Analysis A)

**Date**: 2026-05-21
**Source**: `docs/baseline/data/ipe-n3-detailed.jsonl` (15 IPE runs, full
`problem.json` parsed)
**Related**: `docs/baseline/v0.3.0-rc1-N3.md` (high-level 결과)

이 보고서는 기존 N=3 측정 데이터를 **deeper analysis** (추가 측정 없이) 한
결과. PRINCIPLES.md 룰 1/2/3 검증에 사용 가능.

---

## 1. Failure mode taxonomy

### 1.1 iteration_history 의 failed_node 분포

15 IPE runs 의 `iteration_history` 합산:

| failed_node | retry count | % of total |
|---|---|---|
| **coder** | **59** | **65%** |
| auditor | 11 | 12% |
| generator | 11 | 12% |
| architect | 9 | 10% |
| executor | 1 | 1% |
| **Total iterations** | **91** | 100% |

**관찰**:
- **coder 가 압도적 fail source** (65%) — sample mismatch / Phase B/C fail 모두
  결국 coder 가 다시 작성하라고 routing 됨
- architect 9 retry — M3 dual-call disagreement 또는 sample 구조 invalid
- auditor/generator 각 11 — Phase B/C 진입 후 fail (드물지만 발생)

### 1.2 iteration_history actions

| action | count | % |
|---|---|---|
| retry | 57 | 63% |
| **oscillation_break** | **34** | **37%** |

**핵심 발견**: 안전장치 (`oscillation_break`, R-osc-break / R-coder-osc /
R-phase-a-osc-break 등) 가 전체 iter 의 **37%** 발동. **PRINCIPLES.md §1 의
oscillation hypothesis 데이터 검증** — 누적 안전장치가 흔하게 트리거된다는 신호.

근데 이게 좋은 신호인지 나쁜 신호인지는 양면적:
- 안전장치 없었으면 무한 retry → budget 빨리 소진했을 것 (good)
- 안전장치 발동 자체가 over-correction 패턴 신호 (bad)

---

## 2. LLM call distribution (모든 15 runs 누적)

| node | calls | % | per-run avg |
|---|---|---|---|
| **architect** | **92** | **38%** | 6.1 |
| algorithm_designer | 46 | 19% | 3.1 |
| coder | 41 | 17% | 2.7 |
| reviewer | 41 | 17% | 2.7 |
| auditor | 11 | 4% | 0.7 |
| generator | 11 | 4% | 0.7 |
| evaluator | 3 | 1% | 0.2 |
| **Total** | **245** | 100% | 16.3 |

**관찰**:
- **architect 가 가장 많이 호출됨 (38%)** — M3 dual-call 영향. 한 architect cycle
  = 2 calls (Opus + Sonnet 순차).
- architect 92 calls = 약 46 architect cycles. 그 중 9개 fail (10%). 즉 90%
  architect cycle 은 consensus 통과 — M3 자체는 보통 안정적.
- **evaluator 3** = success 한 3 runs 만 도달. Phase B/C + evaluator 가 IPE 만의
  검증 layer 인데 도달률 낮음.

---

## 3. Per-algorithm cost + retry pattern

| Algorithm | avg cost | avg LLM calls | avg iter | success | most-retry |
|---|---|---|---|---|---|
| Two Sum | $0.78 | 14.0 | 6.0 | 1/3 | coder (9) |
| BFS | $1.07 | 16.3 | 5.0 | 0/3 | coder (7) |
| **Dijkstra** | **$1.31** | 18.3 | 7.0 | 0/3 | **coder (17)** |
| LIS | $0.77 | 16.0 | 6.0 | 0/3 | coder (16) |
| Segment Tree | $1.06 | 17.0 | 6.3 | **2/3** | coder (10) |

**관찰**:
- **모든 algorithm 의 top retry = coder**. IPE 의 모든 fail 이 결국 "wrong sample
  발견 → coder 다시 → 또 wrong" 패턴.
- **Dijkstra: $1.31 / run, coder retry 17번, success 0/3** — baseline 은 3/3 인데
  IPE 가 가장 비싸면서 가장 fail. **multi-mechanism 의 net cost 가 음(-)** 가장
  명확한 사례.
- Segment Tree: success 2/3 (가장 잘 됨). Phase B/C까지 도달 가능한 유일한 알고리즘.

---

## 4. Cost-per-success 비교

| | baseline | IPE | ratio |
|---|---|---|---|
| Total cost (15 runs) | $2.74 | $14.97 | 5.5x |
| Successes | 4 | 3 | -25% |
| **Cost / success** | **$0.69** | **$4.99** | **7.3x** |

**해석**:
- IPE 가 success 1건당 **7.3배 비싼데 quality 는 baseline 보다 떨어짐** (run-level
  -7pp).
- Sample-level 만 +9pp 개선 — 검증 layer 가치는 입증되지만 **운영 비용 대비 가치
  부족**.

---

## 5. Success vs Failure profile

| | n | avg cost | avg LLM calls | avg iter |
|---|---|---|---|---|
| success runs | 3 | $0.94 | 13.3 | 5.3 |
| failure runs | 12 | $1.01 | 17.1 | 6.2 |

**관찰**:
- **fail runs 가 calls + iter + cost 모두 더 사용** — retry cycle 이 cost 만 늘릴
  뿐 결과 향상 X.
- success runs 의 avg iter 5.3 = 단순히 cycle 적게 돈 게 success 와 상관 ↑.
- 즉 **"많이 retry 하면 결국 풀린다" 가설은 데이터로 반박**. 첫 cycle 또는 짧은
  cycle 안에 풀리는 경우만 success.

---

## 6. 주요 인사이트 요약

### 6.1 Coder 가 진짜 bottleneck

65% retry 가 coder 에서 발생. IPE 의 정확한 약점이 coder quality. M1
algorithm_designer 추가했는데도 coder fail 패턴 못 막음. M1 의 ROI 의문.

### 6.2 Multi-mechanism 의 net cost 가 음

- Cost: 7.3x (per success)
- Quality: run-level -7pp, sample-level +9pp
- 단순 산수: cost 7.3x 늘었는데 run-level 떨어짐. **PRINCIPLES.md §3 의
  "baseline ≫ IPE → rollback 검토" 시나리오 부분 진입**.

### 6.3 M3 가 가장 의심스러운 mechanism

- Dijkstra: baseline 3/3 → IPE 0/3
- architect 92 calls (38% of all LLM calls) — 가장 많이 호출되는 노드
- architect retry 9 — fail 의 10%

M3 rollback A/B 측정 → 만약 IPE-without-M3 > IPE-with-M3 면 명확한 rollback
근거. 본 분석 데이터로는 M3 의 net effect 가 음일 가능성 강하게 시사.

### 6.4 oscillation_break 37% 발동

안전장치가 자주 트리거됨. 두 가지 해석:
- 안전장치 없으면 무한 retry 됐을 — 안전장치 가치 있음
- 안전장치가 매번 발동한다는 자체가 over-correction 누적의 패턴 — 시스템 설계
  자체 의문

### 6.5 evaluator 도달률 20% (3/15)

Phase B/C + evaluator 가 IPE 만의 핵심 가치 layer 인데, 80% 가 그 단계 못 도달.
**IPE 의 가치 layer 가 활용되지 않음** — 대부분 Phase A 에서 coder retry 로
budget 소진.

---

## 7. 권장 후속 작업 (PRINCIPLES.md 준수)

### 7.1 단기 (다음 1-2 PR)

| 우선순위 | PR | 근거 (데이터) |
|---|---|---|
| 1 | M3 rollback A/B (single Opus architect) | Dijkstra 3/3 vs 0/3, architect 38% calls |
| 2 | coder budget 6 + max-iter 12 재측정 | coder 65% retry, fail runs avg iter 6.2 |
| 3 | M1 designer ROI A/B (designer off) | 효과 데이터 없음, cost 19% 차지 |

### 7.2 v0.3.0 release 판정 update

기존 보고서 (`v0.3.0-rc1-N3.md`): "tag 보류 + rollback 검토".
본 분석 추가 데이터로 더 강한 신호: **multi-mechanism rollback 1-2개 PR 후 재측정**
필요. 단순 budget tuning 으로는 7.3x cost 차이 줄이기 어려움.

### 7.3 Wider Analysis B/C 권장 여부

- **B (per-mechanism A/B 측정)**: 권장 ✓ — M3 우선. cost ~$6 (5 algo × 3 run /
  mechanism). M3 first → 결과에 따라 M1/M4 추가.
- **C (information bottleneck 정량화)**: 보류 — 본 분석 (#1, #4, #6) 이 이미
  정량 데이터 제공. trace-level 분석은 cost 대비 가치 추가 ↓.

---

## 8. Raw data

- `docs/baseline/data/ipe-n3-detailed.jsonl` — 15 runs full profile (이 PR
  신규)
- `docs/baseline/data/ipe-n3-summary.jsonl` — N=3 PR 의 summary
- `docs/baseline/data/baseline-run{1,2,3}.jsonl` — baseline raw
