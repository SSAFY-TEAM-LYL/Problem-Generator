# Multi-Mechanism (M1~M4) — v0.3.0 RFC + 측정 + rollback 검토

**Last updated**: 2026-05-21
**Scope**: v0.3.0 RFC 의 4 mechanism (M1 sub-agent / M2 pre-hook / M3 multi-model
consensus / M4 adversarial review) 통합 + N=3 baseline 비교 + rollback 검토 상태.
**Status**: M1/M2 운영, **M3 rollback A/B 측정 완료 (net effect 0)**, M4 단독
A/B 미측정.

RFC: [`docs/rfc/v0.3.0_multi-mechanism.md`](../rfc/v0.3.0_multi-mechanism.md)
원본 RCA 4 개는 [`docs/archive/improvements/`](../archive/improvements/) 에 보존.

---

## 0. 개요

v0.3.0 RFC 의 가설: "stochastic LLM-call variance 를 multi-mechanism (M1+M2+M3+M4)
으로 줄여 e2e success ≥ 80% 달성".

baseline N=3 측정 결과:
- IPE run-level: 20% (3/15)
- baseline run-level: 27% (4/15)
- **Δ run-level: -7pp** — hypothesis 부분 반박

IPE 가 sample-level +9pp 우위는 있지만 generation quality 가치 X.
→ "multi-mechanism 의 가치 = 검증 layer (sample correctness)" 로 정정.

---

## 1. 포함된 fix

| Round | Mechanism | 원본 RCA | net effect (N=3 측정) | 상태 |
|---|---|---|---|---|
| 20 | **M2 Pre-Hook** | [`2026-05-19_m2-pre-hook.md`](../archive/improvements/2026-05-19_m2-pre-hook.md) | cost saving (LLM call 전 invalid state reject) | 운영 |
| 21 | **M1 Sub-agent** | [`2026-05-19_m1-sub-agent.md`](../archive/improvements/2026-05-19_m1-sub-agent.md) | quality 측정 안 됨 (단독 A/B 미진행) | 운영 |
| 22 | **M3 Multi-model consensus** | [`2026-05-19_m3-multi-model.md`](../archive/improvements/2026-05-19_m3-multi-model.md) | **net effect 0** (Dijkstra baseline 3/3 vs IPE 0/3) | **rollback 검토** |
| 23 | **M4 Adversarial review** | [`2026-05-20_m4-adversarial-review.md`](../archive/improvements/2026-05-20_m4-adversarial-review.md) | 단독 측정 안 됨 (M3 와 묶여있음) | 운영 |

---

## 2. 각 mechanism 요약

### 2.1 M2 — Pre-Hook (Round 20)

- `ipe/hooks.py` — registry + `register_pre_hook` 데코레이터 + `wrap_with_pre_hooks`
- 3 builtin: `check_problem_complete` (coder 진입 전) / `check_solution_code_present`
  (executor 진입 전) / `check_solution_imports` (stdlib 외 import reject)
- ECC PreToolUse 패턴
- **net effect**: cost saving (invalid state 에서 LLM call 전 reject). quality
  영향 직접 측정 안 됨.

### 2.2 M1 — Algorithm Designer sub-agent (Round 21)

- `ipe/nodes/algorithm_designer.py` — Coder 분해의 designer 측
- 입력: problem + sample + constraints → 출력: `algorithm_design = {name, pseudocode,
  complexity_target, edge_cases}`
- 모델: Sonnet 4.6 (Opus 만큼 깊은 reasoning 필요 X)
- 그래프: architect → algorithm_designer → coder
- **net effect**: 측정 안 됨. coder fail 패턴이 N=3 에서 여전히 65% — designer
  분해가 quality 개선했다는 데이터 없음.

### 2.3 M3 — Multi-Model Consensus (Round 22)

- `ipe/nodes/architect.py` — Opus + Sonnet 순차 dual-call + structural consensus
  voting
- 5-way 결정: match / opus_only / sonnet_only / both_invalid retry / structural
  diff retry
- env var `IPE_DISABLE_M3=1` 로 single-call 우회 (A/B 측정용)
- **net effect (A/B 측정)**:
  - Run-level: 0 (with-M3 3/15, without-M3 3/15)
  - Sample-level: -5.2pp (with-M3 가 더 나쁨)
  - Cost: total 같음, LLM calls -14%, oscillation_break -100%
  - Dijkstra: baseline 3/3 → IPE 0/3 (가장 명백한 음효과)
- **결론**: rollback 정당. v0.3.0 release 전 정식 rollback PR 진행 예정.

### 2.4 M4 — Adversarial Review (Round 23)

- `ipe/nodes/reviewer.py` — Coder solution 을 별도 LLM (Opus) 이 검토
- 그래프: coder → reviewer → {executor (approve) | decision (reject → coder retry)}
- state field: `review_status` / `review_reasoning` / `review_weaknesses`
- graceful approve fallback (parse 실패 시 budget 보호)
- **net effect**: 단독 A/B 측정 안 됨. M3 와 묶여있어 분리 측정 필요.

---

## 3. 측정 데이터 (자세한 내용은 `docs/baseline/`)

| 측정 | 결과 |
|---|---|
| baseline N=3 | 4/15 (27%), sample 78.7%, cost $2.74 |
| IPE-with-M3 N=3 | 3/15 (20%), sample 87.7%, cost $14.97 |
| IPE-without-M3 N=3 | 3/15 (20%), sample 92.9%, cost $15.14 |
| Δ M3 (with vs without) | run 0 / sample -5.2pp / cost +1% / oscillation_break -100% |

핵심 인사이트:
- M3 의 net effect = 0 ~ 음(-) (Dijkstra 3/3 vs 0/3 는 -100%)
- multi-mechanism 의 cost 7.3× per success (baseline 대비)
- IPE 의 진짜 가치는 sample-level 검증 + Catalog / Replay / Sandbox

---

## 4. Rollback trigger (PRINCIPLES.md 룰 5)

| Mechanism | Rollback 조건 (현재 상태) |
|---|---|
| **M3** | net effect ≤ 0 → **충족됨** (rollback PR 예정) |
| M1 | algorithm_designer 단독 disable 측정 후 sample-level 영향 ≤ +3pp → rollback. **미측정** |
| M2 | hook reject 가 coder 의 numpy 같은 invalid import 를 N=3 중 ≥ 1회 차단 → 유지. cost saving 이 본질 |
| M4 | reviewer reject 가 1 cycle 안에 fix 로 이어지는 비율 ≥ 30% → 유지. **미측정** |

---

## 5. 후속 개선 후보

### 5.1 즉시 (이번 release 안)

- **M3 rollback PR** (가장 명백한 음효과). complexity budget +1 회수.
- 그 자리에 skill library (M5) 도입 검토 — algorithm reference implementation
  으로 coder quality 개선.

### 5.2 중기

- M1 단독 A/B 측정 (designer off 모드). cost 19% 차지에 대한 ROI 확인.
- M4 단독 A/B 측정. reviewer reject 의 actionability 정량화.
- coder budget 6 + max-iter 12 재측정 — coder bottleneck (65% retry) 의 budget
  side 해결.

### 5.3 architectural

- **skill library** (`ipe/skills/algorithms/<name>.md`) — ECC skills/ 패턴.
  Coder prompt 에 algorithm-specific reference 동봉 → information bottleneck
  완화.
- 노드 간 통신을 strict schema 로 (free-form JSON → typed protocol). M5 ~ M6
  후보.
