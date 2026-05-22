# IPE v1 PR-A5 — Dijkstra N=3 measurement + Gate 판정 (2026-05-22)

**Date**: 2026-05-22
**Spec**: `docs/PRINCIPLES.md` §3 (baseline anchor) + 룰 1 (N≥3 gate)
**D안 Phase 1 final gate**.
**Data**: `docs/baseline/data/v1-pr-a5-detailed.jsonl` (3 lines, raw JSONL).

---

## 1. 측정 조건

| | value |
|---|---|
| Algorithm | Dijkstra |
| N | 3 |
| `max_iter` | 6 |
| Graph | `ipe/v1/graph.py` (4 노드 + structured routing + DijkstraVerifier) |
| LLMs | Opus 4.7 (architect/coder) + Sonnet 4.6 (designer) |
| Sandbox | docker (default `pick_runner()` auto) |
| Command | `python -m ipe.v1.measurement --algorithm dijkstra --n 3 --output docs/baseline/data/v1-pr-a5-detailed.jsonl --max-iter 6` |

**Pre-측정 incident** (재현 정직성):

- 첫 실행에서 `anthropic.BadRequestError: 'temperature' is deprecated for this
  model` (Opus 4.7 신규 deprecation).
- Fix: `AnthropicArchitectLLM` / `AnthropicDesignerLLM` / `AnthropicCoderLLM`
  의 `temperature=...` 인자 제거 (model default 사용). 본 PR 안에서 동시 commit.
- 재실행 → 본 결과.

---

## 2. 결과

| Metric | IPE v1 N=3 |
|---|---|
| **Run-level success** | **3/3 (100%)** |
| Sample-level pass | 12/12 (100%) |
| `samples_engaged` total | 12/12 (100% verifier 실효 검증) |
| Mean elapsed | ~48.8s per run |
| Iterations per run | **1** (모든 run 첫 시도 통과 — fix loop 진입 0) |
| Invariant violations | 0 |
| Blocking signatures | empty (no fix loop, success 1-shot) |

### 2.1 Per-run detail

| run | status | iter | samples | engaged | elapsed |
|---|---|---|---|---|---|
| r1 | success | 1 | 4/4 | 4 | 48.7s |
| r2 | success | 1 | 4/4 | 4 | 49.9s |
| r3 | success | 1 | 4/4 | 4 | 48.0s |

---

## 3. 비교 (baseline anchor 기준)

| Setup | Run-level | Sample-level | 비고 |
|---|---|---|---|
| baseline v0 N=3 Dijkstra (PR #71) | 3/3 (100%) | 15/15 (100%) | single Opus call, multi-mechanism 없음 |
| IPE v0 N=3 Dijkstra (`v0.3.0-rc1-N3.md`) | **0/3 (0%)** | n/a (architect/coder fail) | M1~M4 multi-mechanism |
| **IPE v1 N=3 Dijkstra (본 측정)** | **3/3 (100%)** | **12/12 (100%)** | typed schema + symbolic verifier + structured routing |

**IPE v1 이 v0 (0/3) → 3/3 으로 회복** + baseline 과 동등. sample count 는 다름
(baseline 5/run vs v1 4/run — architect 가 sample 갯수 자율 결정).

---

## 4. D안 H1/H2/H3 검증

### H1 (typed structured artifacts → fix loop `budget_exhausted` 감소)

- IPE v0 N=3: 3/3 fail (architect / coder budget_exhausted 패턴).
- IPE v1 N=3: 3/3 success, **모든 run `iteration=1`** (fix loop 진입 0).
- → **H1 의 정성적 부분 검증** — single-shot success 자체가 v0 의 multi-iter
  budget 소진 패턴과 대조.
- 정량적 fix loop 측정 (v0 vs v1 의 retry 1회 후 success ratio) 은 fail case
  부재로 본 측정에서는 불가능 → Phase 2 LIS/SegmentTree (더 어려운 algo) 에서.

### H2 (algorithm-specific symbolic verifier → retry feedback 명료성)

- `samples_engaged` 12/12 = verifier 100% 실효 (silent skip 0).
- `invariant_violations` 0 — 정답이라 violation 시그널 자체가 발생 안 함.
- → **H2 의 engagement 부분 검증** (verifier 가 실제로 invariants 강제함).
- feedback 명료성 (violations description 이 LLM 의 fix 에 도움 되는지) 은 fail
  case 부재로 측정 불가 → Phase 2 에서.

### H3 (IterationContext 누적 → skill amnesia 완화)

- 모든 run `iteration=1` → IterationContext 누적 안 됨 (accumulated_lessons /
  failed_strategies 도 비어 있음).
- → **H3 직접 측정 안 됨**. multi-iter run 이 발생하는 Phase 2 algo 에서 측정
  미루어짐.

**요약**:

- ✅ H1 정성적 + H2 engagement 검증
- ⚠ H1 정량적 / H2 명료성 / H3 누적 — fail case 부재로 본 측정 불가, Phase 2
  처리

---

## 5. `PRINCIPLES.md` 룰 적용 결과

| 룰 | 적용 | 결과 |
|---|---|---|
| 1. N≥3 measurement gate | ✓ | N=3 완료 |
| 2. Cross-algorithm regression check | △ | Phase 1 = Dijkstra 만, LIS/SegmentTree 는 Phase 2 verifier 추가 후 의무 |
| 3. Baseline anchor 영구화 | ✓ | baseline 3/3 vs v1 3/3 비교 |
| 4. Complexity budget | △ | v0 7 + v1 4 = 11 임시 공존 (Phase 4 v0 archive 시 회복) |
| 5. RCA rollback 조건 | ✓ | `ipe/v1/__init__.py` 명시 ("N=3 ≤ 0/3 → kill-switch"). 본 측정 3/3 → rollback X |

---

## 6. Gate 판정 (D안 Phase 1 kill-switch 결정)

| 시나리오 | 판정 | 본 측정 |
|---|---|---|
| ≥ 2/3 success | **Phase 2 진입** | ✓ **3/3** |
| 1/3 (회색) | 추가 N=3 측정 | — |
| 0/3 | kill-switch (`ipe/v1/` archive + retrospective) | — |

### 판정: **Phase 2 진입** ✅

`ipe/v1/` archive 발동 X. v1 layer 살아남음.

---

## 7. Phase 2 후보 (PR-A5 후)

- **LIS verifier** (`ipe/v1/verifiers/lis.py`) — Longest Increasing Subsequence
  invariants (monotone subsequence + length optimality vs patience sort golden).
- **SegmentTree verifier** — range query/update 결과 vs naive O(N²) golden.
- **TargetAlgorithm enum 확장** — `LIS` / `SEGMENT_TREE` 등 추가.
- **multi-iter fix loop 측정** — 본 측정에서 fail case 부재로 못한 H1/H2/H3
  정량 검증. LIS/SegmentTree 같은 더 어려운 algo 에서 fix loop 발동되는 데이터.
- **v0 catalog 통합** — success run 을 v1 catalog 로 promote (Phase 3).

---

## 8. 한계

- **N=3 small sample size**. variance large (±10pp 예상). Phase 2 measurement
  는 N=5 권장.
- **All-success 데이터** — fix loop / H1-H2-H3 정량 측정 불가. Phase 2 의 더
  어려운 algo 가 필수 anchor.
- **Cost** 정확 추적 안 됨 (Phase 2 의 `LLMCallTracker` v1 통합 후 측정 가능).
  추정: ~$3-10 (4 LLM calls × 3 runs).
- **Sample count 4/run** — architect 자율 결정 (`min=3, max=5`). baseline 5/run
  과 다름. sample 갯수 정규화 권장 (Phase 2).
- **Sandbox tier** docker auto-pick — RLIMIT fallback 시 결과 differ 가능
  (Phase 2 격리 검증).
- **temperature deprecation** 으로 측정 1차 fail — D안 plan 의 기술 변화
  민감도 신호. langchain-anthropic / anthropic SDK version pin 고려.

---

## 9. 다음 단계

1. **PR-A5 머지** → Phase 1 완료.
2. **v0.4.0-alpha tag 검토** — D안 Phase 1 deliverable lock.
3. **Phase 2 entry**: `feat/v2-lis-verifier` 브랜치 — LIS verifier + measurement.
4. 사용자 결정 대기: v0 archive 시점 / v1 catalog 통합 / observability 강화.

---

## 10. Memory anchor 갱신 필요

본 측정 결과는 사용자의 prior session 메모리 (`project_v030_state.md`,
`feedback_measurement_first.md` 등) 와 narrative 정합 — 새 entry 또는 갱신
권장:

- `project_v1_phase1_pass.md` (신규): D안 Phase 1 Gate 통과, Phase 2 진입.
- `project_v030_state.md` 갱신: "v1 Phase 1 통과 — v0 와 병합/archive 검토" 추가.
