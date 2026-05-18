# R-coder-osc — Coder Oscillation Breaker (결정적 차단)

**Date**: 2026-05-18 (Round 12)
**Scope**: v0.2.1 결정적 fix sprint — Round 11 후 e2e 실측에서 발견된 신규 패턴
**Related**: CHANGES.md §17, REQUIREMENTS.md §5.3 (알려진 한계),
`docs/improvements/2026-05-18_osc-break-deterministic.md` (architect 버전, paired),
`docs/improvements/2026-05-18_gen-cap-deterministic.md` (generator)

---

## 1. 발견

### 1.1 Round 11 e2e 실측 (Docker T1)

R-osc-break + R-gen-cap 머지 직후 Docker(T1) sandbox로 e2e 실측:

| Case | Sandbox | Final | history 마지막 4 entries |
|---|---|---|---|
| BFS | RlimitRunner (T3) | **success** | (정상 cycle) |
| BFS | Docker (T1) | budget_exhausted | `coder/retry × 4`, 모두 sig `add33e43`, "phase A failures: 5/5" |
| Segment Tree | Docker (T1) | budget_exhausted | `coder/retry × 4`, 모두 sig `7ef9ec5e`, "phase A failures: 4/4" |

두 Docker run 모두 **coder가 동일 signature로 4번 반복** → coder budget 4 소진.
Phase A (sample exact match)에서 모든 sample fail → 라우팅 `coder` self-loop →
coder가 다시 같은 잘못된 솔루션 생성. R-osc-break은 architect 한정, R-gen-cap은
Generator 단계라 둘 다 발동 못 함.

### 1.2 R-osc-break과 동형 패턴

| 단계 | architect oscillation (R-osc-break) | coder oscillation (R-coder-osc) |
|---|---|---|
| 실패 노드 | architect | coder |
| 반복 신호 | 같은 architect signature 2회+ | 같은 coder signature 2회+ |
| 원인 | LLM이 같은 문제 재생성 (W4 prompt 무시) | LLM이 같은 솔루션 재생성 (W4 prompt 무시) |
| 결정적 해법 | coder로 swap | architect로 swap |
| paired with | R-coder-osc | R-osc-break |

따라서 R-osc-break과 **같은 메커니즘으로 결정적 차단 가능** — helper 일반화.

---

## 2. 해법 — `_detect_node_oscillation` + `_OSC_SWAP_TARGET`

### 2.1 일반화

기존 `_detect_architect_oscillation`을 node-agnostic으로 일반화:

```python
def _detect_node_oscillation(
    state: ProblemState, node_name: str, current_signature: str
) -> bool:
    if state.get("last_failed_node") != node_name:
        return False
    if not current_signature:
        return False
    history = state.get("iteration_history") or []
    prior = sum(
        1 for r in history
        if r.get("node") == node_name and r.get("error_signature") == current_signature
    )
    return prior >= 1
```

기존 `_detect_architect_oscillation`은 1-line wrapper로 보존 (backward compat).

### 2.2 swap 매핑

```python
_OSC_SWAP_TARGET: dict[str, str] = {
    "architect": "coder",   # R-osc-break (Round 11)
    "coder": "architect",   # R-coder-osc (Round 12) — 신규
}
```

- **대칭 swap**: architect oscillation → coder (다른 솔루션 시도), coder oscillation → architect (다른 problem 생성)
- **auditor/generator는 swap 대상 아님**:
  - auditor는 input 검증 도메인 (반복 = 검증 강화 신호, swap 의미 X)
  - generator는 R-gen-cap이 사전 차단 (oscillation까지 도달 안 함)

### 2.3 `_decision` 통합

```python
# 4. R-osc-break / R-coder-osc: 동일 signature 2회+ oscillation 감지 →
#    _OSC_SWAP_TARGET 매핑으로 강제 라우팅 swap (architect ↔ coder 대칭).
failed = state.get("last_failed_node")
feedback = state.get("feedback_message") or ""
current_sig = _error_signature(feedback)
origin_node = failed
osc_break = False
if (
    isinstance(failed, str)
    and failed in _OSC_SWAP_TARGET
    and _detect_node_oscillation(state, failed, current_sig)
):
    failed = _OSC_SWAP_TARGET[failed]
    osc_break = True
```

- 단일 분기로 두 fix 모두 처리 (DRY)
- history record는 `node=origin_node` 보존, `action="oscillation_break"`
- routing/budget 차감 대상만 swap된 노드로

### 2.4 무한 swap 불가 증명

| Cycle | last_failed_node | history sig | swap? |
|---|---|---|---|
| 1 | coder (sig X) | (empty) | No (history 비어있음) |
| 2 | coder (sig X 동일) | [(coder, X)] | **Yes → architect로 swap** |
| 3 | architect (sig Y, swap된 노드가 응답한 새 sig) | [(coder, X)×2] | No (sig 다름) |
| 4 | architect (sig Y 동일) | [...,  (architect, Y)] | **Yes → coder로 swap** (R-osc-break) |
| 5 | coder (sig Z, 새 sig) | … | No |

핵심: swap된 노드가 응답하면 새 LLM 응답으로 signature 바뀜 → 다음 cycle은 prior count 0 → swap 안 됨. 핑퐁 무한 swap 불가.

---

## 3. 우선순위 + 비용

### 3.1 흐름 비교

**Before (Round 11)**:
```
coder fail (sig X) → coder retry → coder fail (sig X 동일) → coder retry → ...
budget 소진 → budget_exhausted(coder)
```

**After (Round 12)**:
```
coder fail (sig X) → coder retry (budget 4→3)
coder fail (sig X 동일) → R-coder-osc → architect로 swap → architect retry
architect 응답 → 새 problem (다른 sig) → coder 재시도 → ...
```

### 3.2 비용

- 코드 변경 18 lines (graph.py), helper 일반화로 R-osc-break + R-coder-osc 둘 다 동일 분기
- Runtime overhead 0 — dict lookup 1번, history scan은 기존과 동일

---

## 4. 테스트 (+11 unit, +1 integration 수정)

`tests/test_routing_units.py`:

| Class | Tests | 검증 |
|---|---|---|
| `TestDetectNodeOscillation` | 5 | 일반화된 helper — architect/coder 둘 다, wrapper 호환 |
| `TestDecisionCoderOscillationBreaker` | 6 | 첫 fail no swap / second-same swap / route to architect / architect budget 0 → exhausted / 다른 sig no swap / **auditor swap 대상 아님** |

`tests/integration/test_routing.py::test_coder_budget_exhausted_halt`:
- 동일 코드 반복 → R-coder-osc swap 후 architect budget 먼저 소진 → architect budget_exhausted
- assertion 완화: `"coder"` → `"budget exhausted"` (halt 자체는 보장)
- history coder entries 검증은 유지 (원인 노드는 기록 보존)

전체 회귀: **289 passed + 3 skipped** (Round 11의 275 + 본 PR +11 unit + integration 조정).

---

## 5. 한계 + 후속

- **swap 후에도 LLM이 같은 패턴 반복 가능**: architect가 다른 problem 생성하지 않거나, coder가 또 같은 솔루션 만들면 두 노드 budget 둘 다 결국 소진. 이 경우 budget_exhausted halt — 무한 루프 차단은 보장.
- **Phase A 실패 신호의 information content**: "phase A failures: 5/5"만으로는 LLM이 무엇이 틀렸는지 모름. R5 (brute oracle Phase B 활용)로 더 구체적 신호 제공 시 oscillation 자체가 줄어들 수 있음.
- **Docker tier에서 변동성 ↑ 가능성**: RlimitRunner BFS는 success, Docker BFS는 fail. LLM 응답 분포 차이 또는 컨테이너 격리로 인한 timing 차이일 수 있음. 후속 measurement 필요.
- **e2e 실측 (v0.2.1 release 검증)**: BFS + Segment Tree Docker 재실행으로 fix가 실제로 oscillation을 차단하는지 확인. 결정적 unit 검증으로 동작은 보장.
