# R-sig-detail — Phase A Signature Granularity (effective fix for R-coder-osc)

**Date**: 2026-05-18 (Round 13)
**Scope**: v0.2.1 결정적 fix sprint — Round 12 e2e 측정에서 발견된 R-coder-osc effectiveness 한계 해소
**Related**: CHANGES.md §18, REQUIREMENTS.md §5.3,
`docs/improvements/2026-05-18_coder-osc-deterministic.md` (Round 12, paired)

---

## 1. 발견 — R-coder-osc는 작동했지만 effective fix 아니었다

### 1.1 Round 12 SegTree Docker history (실측)

```
run_id: 6bf14c93dd0a, final_status: budget_exhausted, iter: 7

iter=1 node=coder action=retry             sig=7ef9ec5e fb="phase A failures: 4/4"
iter=2 node=coder action=oscillation_break sig=7ef9ec5e fb="phase A failures: 4/4"
iter=3 node=coder action=oscillation_break sig=7ef9ec5e fb="phase A failures: 4/4"
iter=4 node=coder action=oscillation_break sig=7ef9ec5e fb="phase A failures: 4/4"
iter=5 node=coder action=retry             sig=add33e43 fb="phase A failures: 5/5"
iter=6 node=coder action=oscillation_break sig=add33e43 fb="phase A failures: 5/5"
```

**관찰**:
- R-coder-osc는 메커니즘적으로 **정확히 발동** (iter 2/3/4, 6에 action=oscillation_break)
- 각 swap에서 architect로 라우팅 → architect가 새 problem 생성 → coder 재시도
- **그러나 다음 cycle에서 coder가 또 같은 sig로 fail** — swap의 의도 무력화

### 1.2 원인 — feedback granularity 부족

`_error_signature(feedback) = SHA-1(feedback)[:12]`. 그러므로 sig는 feedback 문자열 자체에 의존.

기존 coder routing feedback: `"phase A failures: 4/4"` — failures/total 카운트만 포함.
같은 fail count (4/4)면 problem이 무엇이든 같은 sig.

iter 2: architect swap → 새 문제 → coder fail with `4/4` → sig 7ef9ec5e (이전과 동일)
iter 3: 또 swap → 또 새 문제 → coder fail `4/4` → sig 7ef9ec5e
...

**oscillation_break이 무의미하게 매 cycle 발동** — swap이 effective 한 효과를 못 내고 budget 소진까지 이어짐.

### 1.3 prompt-only fix와의 차이

R10 (history에 "DIFFERENT STRATEGY REQUIRED" 경고) + R13 (Coder LESSON 누적) 등 prompt-side fix는 LLM에 "다르게 하라"고 요청. 하지만 LLM의 fail mode가 같은 X/Y 카운트면 sig 같음 → R-coder-osc 발동 → swap → ... 무의미 루프.

핵심 통찰: **signature가 problem-specific해야** swap의 효과를 측정 가능.

---

## 2. 해법 — `_summarize_phase_a_failure` 추가

### 2.1 helper 함수

```python
_PHASE_A_FIELD_LIMIT = 60  # expected/actual truncate cap

def _summarize_phase_a_failure(r: dict[str, Any]) -> str:
    idx = r.get("index", "?")
    status = r.get("status", "?")
    if status != "OK":
        err = (r.get("stderr") or "")[:60].replace("\n", " ")
        return f"idx={idx}:{status} stderr={err!r}"
    expected = (r.get("expected") or "")[:60].replace("\n", " ")
    actual = (r.get("actual") or "")[:60].replace("\n", " ")
    return f"idx={idx}:OK exp={expected!r} got={actual!r}"
```

**조건 분기**:

| status | 출력 형태 | 근거 |
|---|---|---|
| OK | `idx=<I>:OK exp='<EXPECTED>' got='<ACTUAL>'` | mismatch — 실제 값 비교가 sig 시드 |
| RTE / TLE / MLE | `idx=<I>:<STATUS> stderr='<STDERR_PREFIX>'` | 크래시 — expected/actual 무의미, stderr가 problem-specific |

**truncate**: 60자 cap × 5 samples × 2 fields = ~600자. LLM prompt 부담 없음.
**replace `\n` → ` `**: feedback이 한 줄 표현 유지 (multi-line이면 parser 깨질 가능).

### 2.2 `_build_phase_a_feedback` coder 분기 수정

```python
# Before:
return f"phase A failures: {failures}/{n_total}"

# After:
fails = [r for r in results if not r["pass"]]
details = " | ".join(_summarize_phase_a_failure(r) for r in fails)
return f"phase A failures: {failures}/{n_total} [{details}]"
```

**중요 보존**:
- architect routing 분기 두 개 (`n_pass > 0`, all-fail unique outputs) **byte-identical** → 회귀 0
- 통과한 sample은 details에 미포함 → LLM이 통과한 것까지 다시 쓰지 않도록 신호 명확

### 2.3 흐름 비교

**Before (Round 12)**:
```
iter 1: coder fail (sig X = "4/4") → retry
iter 2: coder fail (sig X 동일) → R-coder-osc swap → architect → new problem
iter 3: coder fail (sig X 동일, 새 문제도 4/4 fail) → swap 또 발동 (무의미)
...
```

**After (Round 13)**:
```
iter 1: coder fail (sig X = "4/4 [idx=0:OK exp='3' got='0', ...]") → retry
iter 2: coder fail (sig X 동일, 같은 problem 같은 fail) → R-coder-osc swap → architect → new problem
iter 3: coder fail (sig Y, 다른 expected → 다른 sig!) → normal retry (정상 cycle)
iter 4: ...
```

R-coder-osc는 진짜 oscillation (같은 문제에서 반복)에서만 발동, swap 후 새 sig가 만들어지면 정상 retry로 복귀.

---

## 3. 테스트 (+12)

`tests/test_phase_a_feedback.py` (신규):

| Class | Tests | 검증 |
|---|---|---|
| `TestSummarizePhaseAFailure` | 5 | OK / RTE / TLE / 긴 expected truncate / `\n` 처리 |
| `TestBuildPhaseAFeedbackCoderRouting` | 5 | failures 카운트 보존 / details 포함 / **다른 problem → 다른 sig** / 같은 results → 같은 sig / 통과 sample 제외 |
| `TestBuildPhaseAFeedbackArchitectRoutingPreserved` | 2 | architect 분기 두 개 byte-identical 보존 |

핵심 회귀 방지 테스트: `test_different_problems_yield_different_signatures` —
같은 4/4 카운트 두 problem의 expected/actual을 완전히 다르게 설정 →
sig가 달라야 함. 이게 R-coder-osc의 effective fix 보장.

전체 회귀: **301 passed + 3 skipped** (Round 12의 289 + 본 PR +12).

---

## 4. 한계 + 후속

- **expected/actual 길이가 LLM prompt 비용**: 60자 cap이지만 5 sample × 2 field = 600자.
  문제별 통계 측정 후 cap 조정 가능.
- **multi-cycle 검증**: e2e 재실측 (BFS + SegTree Docker)으로 R-sig-detail이
  R-coder-osc oscillation 루프를 실제로 깨는지 확인 필요. v0.2.1 release 검증.
- **R12 hang resilience**: Round 12 BFS Docker run에서 Anthropic 529 Overloaded
  crash 발생 → R12 (retry/backoff) 우선순위 **P1 → P0** 승격 필요. R-sig-detail
  머지 후 R12 작업 권장.
- **다른 노드 feedback granularity**: 본 fix는 Phase A coder routing 한정.
  auditor/generator의 feedback도 비슷한 granularity 부족 가능성. measurement 필요.
