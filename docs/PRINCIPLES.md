# IPE Engineering Principles

**Status**: living document (변경 시 PR + CHANGES entry)
**Last updated**: 2026-05-20
**Owner**: IPE maintainers

---

## 0. 목적

LLM 기반 시스템에서 over-correction / oscillation 패턴을 방지하기 위한 운영 룰.
**룰은 코드의 일부**다 — 위반하는 PR은 머지 안 함.

이 문서는 IPE 의사결정 시 참조하는 SSOT (single source of truth). 새 PR이 룰
중 하나를 위반해야 한다면 PR 본문에 명시적으로 정당화 (justification + 측정 근거)
하고, 정책 자체를 함께 업데이트해야 한다.

---

## 1. 배경 — 왜 이 정책이 필요한가

Round 11~23 변경 이력 (요약):

| Round | Fix | 의도 | 발견된 부작용 |
|---|---|---|---|
| 11 | R-osc-break | BFS 결정적 차단 | Segment Tree 0/4 |
| 11 | R-gen-cap | SegTree generator 차단 | (별개 패턴) |
| 12 | R-coder-osc | architect↔coder swap 일반화 | Phase A 무한 oscillation |
| 13 | R-sig-detail | feedback sig 정밀화 | (R-coder-osc 효과 보강) |
| 17 | R-phase-a-osc-break | routing layer 차단 | (BFS swap 1 cycle 한계) |
| 18 | R-coder-parse | fenced block fallback | (crash 차단) |
| 19 | R5 brute oracle | sample expected 검증 | (1 cycle 차단) |
| 20 | M2 Pre-hook | LLM call 전 invalid reject | (cost 절약) |
| 21 | M1 Sub-agent | Coder 분해 | (DoD 측정 시 LIS architect=0 발견) |
| 22 | M3 Multi-model consensus | Architect dual-call | (LIS에서 같은 문제 악화) |
| 23 | M4 Adversarial review | Coder ↔ Reviewer | (Phase 1 1/5 success) |

**관찰된 패턴**:
1. **N=1 measurement 기반 fix가 다른 algorithm에 regression**. 매 fix 사이클이
   새 edge case를 만들고, 다음 cycle에서 그걸 또 fix하려는 안전장치 추가.
2. **Stochastic variance를 deterministic 안전장치로 덮으려는 시도**는 fundamental
   information bottleneck (노드 간 자연어 통신 + stateless LLM call) 을 해결 못함.
3. **누적 복잡도**: 7 nodes + 10+ safety mechanisms + 5 PR sequence. Trace 어려움
   증가, 회귀 risk 증가.

v0.3.0 Phase 1 DoD 측정 (5 algo × 1 run): **1/5 success (20%)**. 80% 목표 미달
의 이유는 budget tuning이 아니라 information bottleneck 누적 가능성. → **단일
LLM baseline 비교 측정 없이는 multi-mechanism의 가치 검증 불가**.

---

## 2. 운영 룰

### 룰 1 — N≥3 measurement gate

**규칙**: 어떤 fix도 1 run 결과만으로 도입 금지. 같은 algorithm × 최소 3 run 측정
후, 패턴이 N≥2에서 재현될 때만 fix 도입.

**왜**: LLM 호출은 비결정적. variance가 LLM 자체 noise인지 진짜 시스템 결함인지
구분 안 됨. 1 run에서 본 fail이 다음 run에서 success일 가능성 항상 있음.

**적용**:
- PR 본문에 `## Measurement` 섹션 의무 — N ≥ 3 run 결과 표 첨부.
- 패턴 미재현 (1/3 fail) 시 fix 보류, 추가 측정 또는 무시.

**예외**: crash / data loss / 보안 issue 는 N=1로도 fix 가능 (variance 무관).

---

### 룰 2 — Cross-algorithm regression check

**규칙**: 특정 algorithm 의 fail을 fix 하는 PR은 다른 4개 (현재 5 anchor: Two Sum,
BFS, Dijkstra, LIS, Segment Tree) 도 각 1 run 추가 측정. **regression 발견 시 fix
보류 또는 scope 축소**.

**왜**: Round 11 R-osc-break (BFS fix → SegTree regression) 같은 over-correction
이 정확히 이 룰이 없어서 발생.

**적용**:
- PR 본문에 `## Cross-algorithm regression` 섹션 — 5 algorithm 측정 결과 표 (before
  PR / after PR / delta).
- regression algorithm 발견 시 PR description에 명시 + roll-back plan 동봉.

**예외**: 측정 cost가 큰 PR (e2e 시간 길어진다)은 PR 한 cycle에 최소 3 algorithm
선택 가능. 단 다음 PR에서 나머지 보강.

---

### 룰 3 — Baseline anchor 영구화

**규칙**: 매 release 마다 "단일 LLM baseline (1 call로 architect+coder+verify)"
측정. 다음 비교 영역에서 baseline ≥ IPE 면 해당 multi-mechanism rollback 검토.

**왜**: IPE의 정당화는 "단일 LLM보다 quality ↑" 또는 "단일 LLM은 못 하는 검증/관측
layer 제공" 중 하나여야 함. baseline 비교 없이는 multi-mechanism이 over-engineering
인지 정당한 가치인지 알 수 없음.

**적용**:
- `docs/baseline/<version>.md` 에 매 release baseline 측정 결과 보관.
- baseline ≫ IPE → multi-mechanism 일부 rollback PR.
- baseline ≈ IPE → IPE는 검증 layer로만 정당화 (Catalog / Replay / Phase B/C).
- baseline ≪ IPE → 현 방향 유효, budget tuning만.

**예외**: 없음. release tag 의 DoD 일부.

---

### 룰 4 — Complexity budget

**규칙**: 그래프 노드 ≤ 8, safety mechanism ≤ 12. 추가하려면 기존 1개 simplify
또는 remove.

**왜**: Round 11~23 누적으로 노드 7 + safety 10 도달. Trace 어려움 + 회귀 risk
증가. budget cap이 없으면 무한 누적.

**적용**:
- PR 본문에 `## Complexity impact` 섹션 — 노드 / safety 카운트 before/after.
- cap 도달 시 PR description에 "어떤 기존 메커니즘을 simplify/remove했는지" 명시.

**현재 카운트** (2026-05-20):
- 노드 7: architect, algorithm_designer, coder, reviewer, auditor, generator, evaluator
- safety 10: R-osc-break, R-gen-cap, R-coder-osc, R-sig-detail, R-phase-a-osc-break,
  R-coder-parse, R5 brute oracle, M2 hooks, M3 dual-call, M4 reviewer

**예외**: 없음. 우회는 정책 자체를 업데이트하는 PR.

---

### 룰 5 — RCA에 롤백 조건 명시

**규칙**: 모든 `docs/improvements/<date>_<name>.md` RCA 문서는 마지막 섹션에
**"Rollback trigger"** 명시. "이 측정 anchor에서 effect 가 보이지 않으면 rollback"
이라는 명시적 조건.

**왜**: fix 가 효과 있는지 사후 검증 가능해야 over-correction 방지. 효과 없는
fix 가 rollback 안 되고 누적되면 룰 4 budget 압박.

**적용**:
- RCA 템플릿: `## Rollback trigger` 섹션 추가.
- 예시: "다음 2 release 의 baseline 비교에서 IPE success rate 향상 없으면 rollback"
- 또는: "Phase 1 e2e 측정 3회 연속 0/5 contribution 이면 rollback"

**예외**: 인프라 fix (sandbox, runner, parsing) 는 rollback trigger 대신 정상 동작
회복 조건.

---

## 3. 단일 LLM baseline 측정 spec

매 release 의 DoD 일부:

```bash
# 5 algorithm × 1 baseline call each (= 5 calls)
# Architecture: 1 Opus call이 problem + solution + sample expected를 한 번에 생성
python -m ipe.baseline run "Two Sum"
python -m ipe.baseline run "BFS"
...
python -m ipe.baseline run "Segment Tree"
```

**baseline LLM prompt 형식**:
- "다음 algorithm 으로 competitive programming problem 을 만들어라. 같은 응답
  안에 problem, sample (input+expected), python solution 모두 포함. solution을
  sample에 실행해서 검증해라."

**측정 metric**:
- Pass rate = `sum(sample_pass) / sum(sample_count)`
- Failure mode = wrong sample / impossible problem / verification skip

**보관**: `docs/baseline/<version>.md`.

---

## 4. 적용 일정

- **즉시**: 이 PR 머지 후 모든 신규 PR이 룰 1~5 적용.
- **다음 PR**: `ipe/baseline/` 모듈 + CLI + 측정 결과 `docs/baseline/v0.3.0-rc1.md`.
- **v0.3.0 release tag**: baseline 측정 결과 vs IPE Phase 1 비교 후 판정.

---

## 5. 위반 사례 처리

- PR 작성자: PR description 에 "이 룰을 위반하는 이유 + 측정 근거" 명시.
- 리뷰어: 룰 위반 발견 시 BLOCK + "rule N (link)" 코멘트.
- 정책 자체 업데이트가 필요하면: 이 문서 수정하는 PR 을 먼저 머지.

---

## 6. 참고

- Round 11~23 RCA: `docs/improvements/2026-05-*.md`
- v0.3.0 RFC: `docs/rfc/v0.3.0_multi-mechanism.md`
- CHANGES log: `CHANGES.md`
