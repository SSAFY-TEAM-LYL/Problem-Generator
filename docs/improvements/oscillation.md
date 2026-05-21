# Oscillation Breakers — Phase A / Coder / Router 결정적 차단 패턴

**Last updated**: 2026-05-21
**Scope**: LLM 응답 variance 로 인한 같은 signature 반복 retry → budget 빠르게
소진 패턴을 결정적으로 차단하는 안전장치 모음
**Status**: 운영 중. PRINCIPLES.md 룰 4 의 complexity budget (safety ≤ 12) 내.

이 문서는 5 개의 oscillation-related fix 를 통합한 SSOT.
원본 RCA 는 [`docs/archive/improvements/`](../archive/improvements/) 에 보존.

---

## 0. 개요

LLM 응답이 비결정적이라 같은 prompt 에 동일 알고리즘 misunderstanding 으로
반복 fail. naive retry 만 의지하면:
- 같은 signature 의 retry → 같은 fail → budget 소진
- 또는 더 나쁜 응답으로 swap → 무한 oscillation

대응: **error_signature 기반 결정적 차단** + **routing layer 안전장치** + brute
oracle 기반 sample 정확성 검증.

---

## 1. 포함된 fix

| Round | Fix | 원본 RCA | 작동 layer | 상태 |
|---|---|---|---|---|
| 11 | R-osc-break | [`2026-05-18_osc-break-deterministic.md`](../archive/improvements/2026-05-18_osc-break-deterministic.md) | decision (architect ↔ coder swap) | 운영 |
| 11 | R-gen-cap | [`2026-05-18_gen-cap-deterministic.md`](../archive/improvements/2026-05-18_gen-cap-deterministic.md) | generator validator | 운영 |
| 12 | R-coder-osc | [`2026-05-18_coder-osc-deterministic.md`](../archive/improvements/2026-05-18_coder-osc-deterministic.md) | decision (coder → architect swap, 일반화) | 운영 |
| 13 | R-sig-detail | [`2026-05-18_sig-detail.md`](../archive/improvements/2026-05-18_sig-detail.md) | error_signature granularity | 운영 |
| 17 | R-phase-a-osc-break | [`2026-05-19_phase-a-osc-break.md`](../archive/improvements/2026-05-19_phase-a-osc-break.md) | Phase A routing | 운영 |
| 19 | R5 brute oracle | [`2026-05-19_r5-brute-oracle-phase-a.md`](../archive/improvements/2026-05-19_r5-brute-oracle-phase-a.md) | Phase A sample 검증 | 운영 |

---

## 2. 공통 패턴

### 2.1 error_signature

`_history.py` 의 `error_signature` = `feedback_message` 의 SHA-1 hash 앞 12자.
같은 fail 패턴은 같은 sig.

R-sig-detail (Round 13) 가 signature granularity 를 강화 — Phase A fail 시
sample index + expected/actual prefix 까지 sig 에 포함. 같은 algorithm 의
다른 sample 에서 fail 해도 sig 가 달라짐.

### 2.2 oscillation 감지 임계

```python
def _detect_node_oscillation(state, node_name, current_signature):
    # 현 cycle 의 last_failed_node == node_name 이고
    # 같은 signature 가 iteration_history 에 1회+ (이번 포함 2회+) 있으면 True
```

### 2.3 swap target

| 노드 | swap 대상 | 이유 |
|---|---|---|
| architect | coder | BFS 결정적 차단 (Round 11) |
| coder | architect | Phase A oscillation 차단 (Round 12 일반화) |

auditor/generator 는 swap target X — 도메인 다름 (input validation /
generator-cap 별도 sub-layer).

### 2.4 routing layer 추가 안전장치 (Round 17)

R-phase-a-osc-break: `_decide_phase_a_route` 가 history 를 보고 같은 sig 로
architect 라우팅이 2회+ 누적 시 coder 강제. 기존 R-osc-break (decision swap)
이 cover 못 한 layer.

### 2.5 sample 검증 결정적화 (Round 19)

R5 brute oracle: Phase A fail 시 brute solution 을 sample stdin 에 실행 →
architect expected 의 정확성을 LLM 노이즈 외부에서 결정적 검증. brute 가 모든
sample confirm 시 coder 강제 (1 cycle).

---

## 3. 라우팅 행동 요약

```
coder solution 실행
  ↓ Phase A
  ├─ 다수 통과 + 소수 fail → architect (sample 의심)
  │    └─ 같은 sig 2회+ → coder 강제 (R-osc-break / R-phase-a-osc-break)
  │    └─ brute 모든 sample confirm → coder 강제 (R5, 1 cycle)
  ├─ 전체 fail + unique outputs → architect (R-osc-break 대상)
  └─ 다수 fail + crash → coder (R-coder-osc 대상)
```

---

## 4. 측정 데이터 (N=3)

- 전체 IPE 15 runs 의 `iteration_history` 91 entries 중
  - retry: 57 (63%)
  - **oscillation_break: 34 (37%)**
- 안전장치 활발히 발동. 단 IPE-without-M3 N=3 측정에서는 0건 — M3 dual-call 이
  trigger 의 주된 원인이었음 (자세한 내용 `docs/baseline/m3-rollback-ab.md`).

---

## 5. Rollback trigger (PRINCIPLES.md 룰 5)

| 안전장치 | rollback 조건 |
|---|---|
| R-osc-break | iteration_history 에서 oscillation_break 발동률 ≥ 10% 인 release 가 3 회 연속이면 → decision swap 자체가 over-correction 이 됨. swap target 매핑 재검토 |
| R-coder-osc | 위와 동일 |
| R-sig-detail | sig granularity 가 너무 미세해 swap 영향 없으면 rollback |
| R-phase-a-osc-break | routing layer 의 swap 이 1 cycle 이내에 fix 로 이어지지 않으면 rollback |
| R-gen-cap | generator validator 가 generator 자체 fail 보다 많이 reject 하면 rollback (false positive cap) |
| **R5 brute oracle** | brute 가 모든 sample confirm 한 cycle 의 coder 강제가 success 로 이어지는 비율 ≥ 50% 이어야 함. 아니면 rollback (brute oracle 신뢰도 부족) |

---

## 6. 후속 개선 후보

- **oscillation_break 발동률 정량 측정** — 매 release 마다 metric 수집해 PRINCIPLES.md
  룰 4 의 budget 정당성 검증.
- R-phase-a-osc-break / R-osc-break 통합 (둘 다 routing layer / decision layer
  의 같은 패턴). complexity budget +1 회수 가능.
- R5 brute oracle 을 Phase B 까지 확장 (현재 Phase A 만).
