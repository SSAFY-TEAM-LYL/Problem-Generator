# R-phase-a-osc-break — Phase A 라우팅 무한 반복 결정적 차단

**Date**: 2026-05-19 (Round 17)
**Scope**: v0.2.1 release 전 발견된 Phase A 라우팅 패턴 — R-osc-break의 effectiveness 한계 보완
**Related**: CHANGES.md §22,
`docs/improvements/2026-05-18_osc-break-deterministic.md` (Round 11 — paired, _decision 단계),
`docs/improvements/2026-05-18_docker-mount-fix.md` (Round 16 — 본 측정의 prerequisite)

---

## 1. 발견 (Round 16 BFS run 1)

인프라 fix 완료 후 진짜 e2e 측정:

```
BFS run_id 7e9f123fab09: final=budget_exhausted, iter=7

iter=1 architect retry           sig=56071271 fb=phase A: 4/5 passed but 1 mismatched
iter=2 architect retry           sig=86f1b541 fb=phase A: 3/5 passed but 2 mismatched
iter=3 architect oscillation_break sig=56071271 (이전 sig 재등장)
iter=4 architect oscillation_break sig=56071271
iter=5 architect oscillation_break sig=56071271
iter=6 architect oscillation_break sig=56071271
```

R-osc-break (Round 11)는 정확히 발동 (iter 3~6 모두 action=oscillation_break)
했지만 budget_exhausted까지 갔다.

---

## 2. 진짜 원인 — Phase A 라우팅이 architect를 매 cycle 다시 선택

`_decide_phase_a_route` (executor.py:188):

```python
# (a) 0 < n_pass < n_total + no crash → architect (sample wrong 의심)
# (b) all fail + all OK + unique → architect
# (c) else → coder
```

BFS 4/5 패턴 = 분기 (a) → 매번 architect 반환.

### 2.1 R-osc-break의 swap이 1 cycle만 지속

| step | 상태 |
|---|---|
| _decide_phase_a_route | target = architect (분기 (a)) |
| _decision.swap | failed swap to coder (R-osc-break) |
| coder 실행 | new solution 시도 |
| executor 재실행 | Phase A 결과 → 또 4/5 → 분기 (a) → architect |
| _decision.swap | 또 R-osc-break 발동 |
| ... | 무한 반복 + budget 소진 |

R-osc-break은 `_decision`의 swap 단계 처리 → swap된 cycle만 coder 진입.
그러나 그 다음 cycle의 routing은 `_decide_phase_a_route`가 결정 → 다시
architect. swap 무한 발동.

### 2.2 왜 SegTree는 success였나

SegTree는 architect가 sample을 올바르게 만들었고 (analytical computation 가능),
coder가 첫 시도에 통과 → Phase A 통과 → Phase B/C 진입 → success. Phase A
oscillation 진입 안 함.

BFS는 graph traversal 결과를 architect가 hand-compute 시도하다 1개 sample
expected_output을 잘못 산정 → 무한 반복 진입.

---

## 3. 해법 — Phase A routing 자체에 history 인지

```python
def _decide_phase_a_route(results, state):
    # 기본 분기 (a/b/c) — 기존 동일
    if 0 < n_pass < n_total and not has_crash:
        base = "architect"
    elif n_pass == 0 and all_ok and unique_outputs and n_total >= 2:
        base = "architect"
    else:
        return "coder"

    # R-phase-a-osc-break (Round 17)
    if base == "architect":
        from ipe.graph import _error_signature  # lazy: 순환 import 회피
        feedback_msg = _build_phase_a_feedback(results, base)
        sig = _error_signature(feedback_msg)
        history = state.get("iteration_history") or []
        prior = sum(
            1 for h in history
            if h.get("node") == "architect"
            and h.get("error_signature") == sig
        )
        if prior >= 2:  # 이번 포함 3회+
            return "coder"

    return base
```

### 3.1 threshold = 2 (이번 포함 3회+)

| count | 의미 |
|---|---|
| 1회 | 일반 retry. architect가 sample 고칠 첫 기회 |
| 2회 | R-osc-break이 swap 발동 (cool-down) |
| **3회+** | architect가 sample을 못 고치는 것 확정 → coder 강제 |

threshold 1 (즉시 강제) = 너무 빠름 (false positive). threshold 3+ = 너무 늦음 (budget 소진).

### 3.2 R-osc-break과 보완

| 메커니즘 | 위치 | 효과 |
|---|---|---|
| R-osc-break (Round 11) | `_decision.swap` | 라우팅 후 swap (1 cycle 효과) |
| **R-phase-a-osc-break (Round 17)** | `_decide_phase_a_route` | 라우팅 target 자체 변경 (영속) |

둘이 함께: routing 결정 (R17) + 결정된 routing의 swap (R11) → 두 층 결정적
차단.

### 3.3 lazy import — 순환 회피

`ipe.graph._error_signature`는 graph.py의 private function. `ipe.nodes.executor`
가 top-level에서 import하면 순환 (graph → nodes → executor → graph). 함수 body
안에서 lazy import:

```python
from ipe.graph import _error_signature
```

해시 계산만 필요해서 inline `hashlib.sha1(...).hexdigest()[:12]` 도 가능했지만,
graph의 sig 로직이 바뀔 때 sync 위험 → import 채택.

---

## 4. 테스트 (+9)

`tests/test_phase_a_feedback.py::TestDecidePhaseARouteWithHistory`:

| Test | 검증 |
|---|---|
| `test_empty_history_uses_base_routing_architect` | history 비어있으면 기존 분기 |
| `test_one_prior_arch_same_sig_still_architect` | 1회 (이번 포함 2회) → 임계 미만 |
| `test_two_prior_arch_same_sig_forces_coder` | **2회 (이번 포함 3회) → coder 강제** |
| `test_two_prior_different_sig_still_architect` | 다른 sig만 누적 → carry-over 없음 |
| `test_two_prior_coder_same_sig_no_swap` | coder 노드 history는 architect breaker 트리거 안 함 |
| `test_branch_b_also_subject_to_break` | 분기 (b) all-fail-unique도 적용 |
| `test_branch_c_unaffected_by_history` | 분기 (c) crash → history 무관, 항상 coder |
| `test_empty_results_returns_coder` | 기존 동작 보존 |
| `test_no_iteration_history_key_treated_as_empty` | state에 key 없음 → 빈 list |

전체 회귀: **331 passed + 3 skipped** (Round 16의 322 + 본 PR +9).

---

## 5. 메타-교훈 (Round 11~17 series)

### 5.1 결정적 fix는 layer 단위로 발견됨

| Round | 발견 시점 | layer |
|---|---|---|
| 11 R-osc-break | v0.2.0 release 후 | `_decision.swap` (routing 결과 후 swap) |
| 12 R-coder-osc | Round 11 측정 | 같은 layer, 다른 노드 |
| 13 R-sig-detail | Round 12 측정 | observability (feedback granularity) |
| 14 R12 retry | Round 13 측정 | infra (API 재시도) |
| 15 R-docker-workdir | Round 14 measurement (R-sig-detail이 stderr 노출) | infra (workdir path) |
| 16 R-docker-mount | Round 15 측정 | infra (file mount) |
| **17 R-phase-a-osc-break** | **Round 16 측정** | **`_decide_phase_a_route` (routing 결정 layer)** |

R-osc-break (`_decision.swap`)이 잡지 못하는 패턴이 `_decide_phase_a_route`에
있었다. routing 결정은 두 layer 모두 cover해야 무한 반복 차단 완전.

### 5.2 observability + 인프라 fix → 진짜 routing 패턴 노출

Round 13 R-sig-detail (feedback granularity) → Round 15 R-docker-workdir →
Round 16 R-docker-mount → **이제서야 routing layer의 진짜 동작 보임**.
이전엔 인프라 버그가 모든 측정을 마스크.

### 5.3 측정-fix loop

Round 11~17 일관된 패턴:
1. fix 머지
2. 즉시 e2e 측정
3. 새 패턴 발견
4. 다음 round fix

"누적된 fix 후 한 번에 측정"이 아니라 매 round 즉시 측정 → 누적 misdiagnosis
회피. 본 series의 핵심 성공 요인.

---

## 6. 한계 + 후속

- **coder가 wrong sample에 적응 시도**: R17이 강제하는 coder 라우팅 후
  coder는 "잘못된 expected를 알면서 맞추는 솔루션" 생성 시도. 정확성 ↓ 가능.
  v0.2.2 candidate: brute oracle Phase B 활용 (R5)으로 sample expected
  재계산 → architect에 정확한 정보 제공이 더 근본적.
- **threshold 2 (이번 포함 3회+) tuning**: BFS 측정 1회 기반. 다른 알고리즘
  케이스에서 false positive/negative 측정 시 조정 가능.
- **R-coder-parse 신규 backlog**: BFS run 2에서 `Coder response has no fenced
  code block` crash 발견. LLM이 가끔 fenced block 누락 → graceful fallback
  필요. v0.2.2 candidate.
- **e2e 재실측 필요**: 본 fix 후 BFS 재실측 → R-phase-a-osc-break이 실제로
  무한 반복 차단하는지 확인 → v0.2.1 release.
