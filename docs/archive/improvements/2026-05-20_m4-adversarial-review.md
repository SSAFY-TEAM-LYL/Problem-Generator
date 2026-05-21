# M4 — Adversarial Review (Solution → Reviewer gate, v0.3.0 RFC PR #4)

**Date**: 2026-05-20 (Round 23)
**Scope**: v0.3.0 RFC §M4 구현 — ECC `santa-loop` / `code-reviewer` adversarial
패턴을 Coder 산출물 검증에 적용
**Related**: CHANGES.md §29, `docs/rfc/v0.3.0_multi-mechanism.md` §2 M4

---

## 1. 동기

### 1.1 Executor sample run의 한계

기존 파이프라인은 Coder → Executor 직진. Executor가 sample input에 솔루션을
실행해 expected_output과 비교 (Phase A). 통과하면 Phase B/C adversarial inputs로.

문제: **sample run으로는 안 잡히는 약점들이 많다**.
- complexity가 잘못된 솔루션 (sample 5개에선 다 통과하지만 N=10^5에서 TLE)
- 누락된 edge case (sample이 거기 포함 안 됨)
- IO 최적화 부족 (`input()` 루프 → 큰 입력에서만 TLE)
- off-by-one / overflow / 코드 quality 버그

Round 22 BFS smoke 사례: sample 5개 중 4 pass / 1 wrong answer
(expected=8, actual=-1). architect는 dual-consensus로 정확한 문제 생성했지만
**coder의 솔루션 quality 자체가 부족**. M3는 이 영역을 cover 못 함.

### 1.2 ECC adversarial pattern

ECC `santa-loop` 패턴: generator가 만든 결과를 discriminator (다른 LLM)가
adversarial 관점에서 검토 → reject 시 generator가 retry. 두 LLM의 cross-check가
quality bar.

IPE 적용: **Coder를 generator로, Reviewer를 discriminator로**. Coder가 만든
solution code를 Reviewer (Opus)가 검토 → approve면 진행, reject면 weaknesses를
Coder feedback에 동봉하여 다시.

---

## 2. 설계

### 2.1 그래프 topology

```
Before: ... → coder → executor → decision → ...
After:  ... → coder → reviewer ─approve─→ executor → decision → ...
                          └─reject─→ decision (last_failed_node="coder")
                                          ↓
                                        coder (retry with weaknesses)
```

핵심 결정: **reviewer reject는 decision으로 라우팅**. 다음 이점:
1. decision의 budget 차감 / iteration_history / cost guard 로직을 reviewer reject
   에도 자동 적용 — 별도 budget 관리 불필요
2. R-osc-break / R-coder-osc 같은 oscillation 안전장치 그대로 작동 (same signature
   계속 reject → swap target으로 architect 라우팅)
3. 기존 conditional_edges 구조 재사용 — `_route_after_review`만 신규

### 2.2 Reviewer 노드 인터페이스

**입력 (state)**:
- `problem_description`, `constraints`, `sample_testcases`
- `solution_code` (Coder 산출물)
- `algorithm_design` (선택, M1 산출물 — Reviewer가 design vs solution cross-check
  에 활용 가능)
- `target_language`

**LLM call**: Opus (`REVIEWER_MODEL = "claude-opus-4-7"`). adversarial 추론이
필요하므로 깊은 reasoning 모델 선택.

**출력 JSON**:
```json
{
  "verdict": "approve" | "reject",
  "reasoning": "one-sentence summary",
  "weaknesses": ["concrete weakness 1", "concrete weakness 2", ...]
}
```

**state 신규 필드**:
- `review_status: str` — "approved" | "rejected"
- `review_reasoning: str` — 한 문장 요약 (분석/관측용)
- `review_weaknesses: list[str]` — reject 시 coder feedback에 동봉

### 2.3 경로 결정

| 분기 | 조건 | 액션 |
|---|---|---|
| 1 | `solution_code` 없음 | 보수적 reject (LLM call 없이) — state invariant 깨짐 |
| 2 | parse 실패 | **graceful approve** — Executor가 잡음. budget 보호. |
| 3 | non-dict JSON | graceful approve |
| 4 | verdict = "approve" | approve, executor 진입 |
| 5 | verdict = "reject" | reject + weaknesses를 coder feedback에 동봉 |
| 6 | 알 수 없는 verdict | graceful approve (보수적 reject보다 budget 우선) |

**graceful approve의 이유**: 너무 strict한 Reviewer가 budget을 빨리 소진하면
오히려 final_status=budget_exhausted가 늘어남. parse 실패 / 모호한 verdict는
보수적으로 통과시키고, Executor + Phase B/C가 진짜 버그를 잡도록 위임. Reject은
**확신할 때만** 발동.

### 2.4 Prompt 설계 핵심

System prompt 핵심 지침:
- **"Be specific"** — vague concerns ("could be slow", "maybe overflow")는
  actionable이 아니라 reject 사유 X. 구체 input + symptom 명시 요구.
- **"If unsure → approve"** — 모호하면 통과. Executor + Phase B/C가 catch.
  Reject는 강한 신호여야 budget 가치.
- **Minor style은 reject 사유 X** — correctness/coverage만이 reject 기준.

### 2.5 NodeRetryBudget 불변

Reviewer는 self-loop 안 함 (reject 시 coder로 cross-route). 따라서:
- `NodeRetryBudget`에 reviewer 추가 X
- `_RETRY_TARGETS` 불변 (`architect`, `algorithm_designer`, `coder`, `auditor`,
  `generator`)
- conditional_edges에 reviewer 분기 추가 안 함 (decision에서 reviewer로 가는 경로 X)

Coder 측 budget이 reviewer rejection 사이클도 흡수 — 같은 sig로 reject 누적되면
budget_exhausted로 자연스럽게 종료.

---

## 3. ECC mapping

| ECC primitive | IPE M4 구현 |
|---|---|
| `santa-loop` adversarial | Coder (generator) ↔ Reviewer (discriminator) |
| `code-reviewer` agent | Reviewer 노드 (LLM-as-adversary) |
| Cross-validation | sample run + reviewer feedback 둘 다 거쳐야 진짜 통과 |
| Graceful degradation | parse 실패 시 approve (budget 보호) |

---

## 4. 변경 파일

| 파일 | 변경 |
|---|---|
| `ipe/nodes/reviewer.py` | 신규 노드 (+~220 lines) — `_approve` / `_reject` / `_format_samples` / `_format_design` / `run` |
| `ipe/llm.py` | `REVIEWER_MODEL` 상수 |
| `ipe/state.py` | `review_status` + `review_reasoning` + `review_weaknesses` |
| `ipe/graph.py` | `reviewer` 노드 등록 + edge + `_route_after_review` |
| `tests/test_reviewer.py` | 신규 (+16) — format / approve/reject / 5 run paths |
| `tests/integration/_helpers.py` | `REVIEWER_APPROVE_RESPONSE` + `REVIEWER_REJECT_RESPONSE` mock + wire 6→7 노드 |

---

## 5. 검증

### 5.1 단위 테스트 (+16)

- `TestFormatSamples` ×3: empty / single / 5 cap
- `TestFormatDesign` ×3: None / with design / without edge_cases
- `TestApproveReject` ×2: approve clears signals / reject routes back
- `TestRun` ×8: approve / reject / missing solution / unparseable /
  non-dict / unknown verdict / design in prompt / 1 LLM call recorded

### 5.2 회귀 0

전체 pytest: **417 passed + 3 skipped** (+16 신규, 회귀 0). ruff 0 / mypy --strict 0.

기존 통합 테스트 5개 자동 호환 — `wire_all_chats_normal` /
`wire_all_chats_forbid_invoke` helpers 가 reviewer mock을 자동 포함하므로
caller 변경 불필요.

---

## 6. 후속 작업

### 6.1 v0.3.0 release (다음)

DoD: 5 algorithm (Two Sum / BFS / Dijkstra / LIS / Segment Tree) × 3 run = 15
runs. 성공률 ≥ 80% (12+/15) 충족 시 v0.3.0 tag.

### 6.2 측정 plan

다음 e2e 측정 시 observability 수집:
- **review rejection rate**: 전체 review call 대비 reject 비율
- **false rejection 발견**: reject된 솔루션을 강제로 executor 돌려서 실제로
  fail하는지 측정 (= Reviewer가 정확한지)
- **rejection feedback 활용도**: reject 후 Coder가 다음 iteration에서 weaknesses
  를 실제 fix하는지 (= weaknesses의 actionability)

이 데이터로 M4가 실제 quality 향상에 기여했는지 정량 검증.

### 6.3 알려진 한계

- **observability gap**: `review_status` / `review_reasoning` / `review_weaknesses`
  가 `problem.json` 에 저장 안 됨 (save_result가 명시적으로 직렬화 안 함). M3
  `architect_consensus` 와 동일 패턴 — Catalog 영속화 PR에서 함께 해결 예정.
- **reject budget interaction**: Reviewer가 매번 reject 시 coder budget 빨리
  소진. 운영 측정 후 budget 조정 필요할 수 있음 (e.g. coder budget 4 → 6).
