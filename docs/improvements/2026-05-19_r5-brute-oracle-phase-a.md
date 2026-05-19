# R5 — Brute Oracle Phase A cross-check (sample-wrong 진단 결정적화)

**Date**: 2026-05-19 (Round 19, v0.2.2 진입)
**Scope**: v0.2.1 release 후 BFS variance 본질 진단의 결정적 보완
**Related**: CHANGES.md §24,
`docs/improvements/2026-05-19_phase-a-osc-break.md` (Round 17 — 보완),
`docs/improvements/2026-05-18_osc-break-deterministic.md` (Round 11)

---

## 1. 동기 (v0.2.1 release 후 측정 분석)

Round 11~18에서 적용한 결정적 fix 9종은 의도 패턴 (oscillation, parse fail, infra)을 정확히 차단했지만, **BFS variance의 진짜 원인 진단은 못 함**:

| Phase A 결과 | 기존 진단 | 진짜 원인 |
|---|---|---|
| 4/5 pass + 1 mismatch | "sample expected_output likely wrong" (분기 a → architect) | **알 수 없음**: architect의 hand-compute 오류일 수도, 진짜 sample 모호성일 수도, golden bug일 수도 |

R-osc-break (Round 11) + R-phase-a-osc-break (Round 17)이 무한 반복은 차단하지만 budget 소진 후 fail. **진단 자체가 잘못된 가설 (sample wrong) 위에 build됨**.

### 핵심 통찰

Coder는 R15 (Sprint 3)부터 `brute_solution_code`를 동시 작성:
- naive 알고리즘 (O(N²) 등)
- small sample (sample stdin은 N ≤ 5)에 대해 빠르게 정답 산출
- golden보다 단순하지만 결정적 정답

**Phase A에서 brute가 architect expected와 비교 → architect 정확성 결정적 검증** 가능.

---

## 2. 해법 — `_run_brute_on_samples` + Phase A routing 통합

### 2.1 새 helper

```python
def _run_brute_on_samples(*, brute_code, samples, runner, workdir, language,
                          time_limit, memory_limit) -> list[dict] | None:
    brute_dir = workdir / "brute_oracle"
    brute_dir.mkdir(parents=True, exist_ok=True)
    _write_source(brute_dir, language, brute_code)
    ok, _ = _compile(runner, brute_dir, language)
    if not ok:
        return None  # brute fallback
    out = []
    for idx, tc in enumerate(samples):
        res = _execute_solution(runner, brute_dir, language,
                                stdin_text=tc["input"],
                                time_limit_ms=time_limit, memory_limit_mb=memory_limit)
        out.append({
            "index": idx,
            "status": res.status,
            "output": _normalize(res.stdout),
            "matches_expected": res.status == "OK" and _normalize(res.stdout) == _normalize(tc["expected_output"]),
        })
    return out
```

별도 `workdir/brute_oracle/` subdir → 기존 run_dir (golden 코드) 안 건드림.

### 2.2 분기 매트릭스

| Phase A | brute oracle | 진단 | routing |
|---|---|---|---|
| fail (분기 a 또는 b) | **모든 sample OK + matches_expected=True** | architect 정확 + **golden bug** | **coder 강제** |
| fail | brute가 architect와 다른 답 일관 | architect expected 오류 | architect + brute feedback |
| fail | brute RTE/일부 fail | unreliable | 기존 분기 |
| fail | brute 없음 | unknown | 기존 분기 |

### 2.3 `_decide_phase_a_route`에 brute 조건 삽입

```python
# base 결정 (기존 분기 a/b/c)
...
# R5: brute가 모든 sample 확정 → coder 강제
if base == "architect" and brute_results:
    all_brute_confirm = (
        len(brute_results) == n_total
        and all(b.get("status") == "OK" for b in brute_results)
        and all(b.get("matches_expected") is True for b in brute_results)
    )
    if all_brute_confirm:
        return "coder"
# R-phase-a-osc-break (Round 17): fallback
...
return base
```

순서:
1. base 결정 (a/b/c)
2. **R5 brute confirm → coder 강제** (있을 때만)
3. R-phase-a-osc-break (history 3회+) → coder 강제 (brute 없을 때 fallback)
4. base 그대로 (정상 retry)

### 2.4 Feedback enrichment

```python
def _enrich_with_brute_oracle(base, results, brute_results):
    if not brute_results:
        return base
    mismatches = [
        f"idx={r['index']}: architect expected={r['expected']!r} "
        f"but brute oracle gave {b['output']!r}"
        for r, b in zip(results, brute_results)
        if not r.get("pass") and b.get("status") == "OK" and not b.get("matches_expected")
    ]
    if not mismatches:
        return base
    return base + " | brute oracle disagrees: [" + " ; ".join(mismatches) + "]"
```

architect routing 시 brute가 다른 답을 produce한 sample에 대해 architect feedback에 brute output 노출 → architect가 sample expected를 brute 값으로 수정 가능.

---

## 3. R-phase-a-osc-break과 보완

| Fix | 발동 | 비용 |
|---|---|---|
| **R5 (Round 19)** | brute 있음 + 모든 sample match | **첫 cycle**부터 결정 |
| R-phase-a-osc-break (Round 17) | history에 같은 sig 2회+ 누적 | 3 cycle 후 |

R5가 brute 있을 때 우선 적용. brute 없으면 R-phase-a-osc-break이 fallback (history-driven).

---

## 4. 테스트 (+9)

`tests/test_phase_a_feedback.py`:

`TestPhaseARouteWithBruteOracle` (6):
- `test_no_brute_results_uses_base_routing` (회귀 0)
- `test_brute_confirms_architect_expected_forces_coder` (R5 핵심)
- `test_brute_disagrees_with_architect_keeps_architect_routing`
- `test_brute_compile_fail_returns_none_uses_base` (fallback)
- `test_brute_with_rte_status_ignored` (일부 fail 무시)
- `test_brute_force_overrides_phase_a_osc_break` (R5가 R17보다 먼저)

`TestPhaseAFeedbackWithBruteOracle` (3):
- architect feedback에 brute output enrichment
- brute 없으면 기존 형식 (회귀 0)
- coder routing에는 brute info 추가 안 함

전체: **342 passed + 3 skipped** (v0.2.1의 333 + 본 PR +9).

---

## 5. 한계 + 후속

- **brute 자체 정확성 의존**: Coder가 만든 brute가 잘못된 알고리즘이면 R5도 잘못된 신호. 그러나 brute는 naive (직관적, 검증 쉬움)라 LLM이 골든보다 정확할 가능성 높음.
- **brute 비용**: sample 5개 × ~50ms = 250ms per Phase A 실패. 무시할 수준.
- **brute 없는 케이스**: Coder가 brute를 안 만들면 (R15 optional) R5 비활성 — R-phase-a-osc-break이 fallback.
- **e2e 측정 필요**: 본 fix 후 BFS 재실측 → sample-wrong oscillation 패턴이 첫 cycle에 해소되는지 확인.
- **v0.2.2 candidate**: Sub-agent (Coder 분해), Multi-model consensus (Architect voting) 등 ECC-style 추가 메커니즘.
