# R-coder-parse — Coder fenced block 누락 graceful fallback

**Date**: 2026-05-19 (Round 18)
**Scope**: e2e crash 방지 — LLM이 가끔 fenced block 없이 응답하는 패턴 (Round 16 BFS variance run에서 발견)
**Related**: CHANGES.md §23

---

## 1. 발견

### 1.1 Round 16 BFS variance run crash

R-docker-mount 머지 후 BFS Docker 첫 run은 budget_exhausted (Round 17 R-phase-a-osc-break 동기). variance 확인용 두 번째 run에서 crash:

```
File "ipe/nodes/coder.py", line 119, in _parse_response
    raise ValueError("Coder response has no fenced code block")
ValueError: Coder response has no fenced code block
During task with name 'coder' and id '38fc2ae8-6d09-55b9-c3dc-98d83cc429b3'
```

LLM이 가끔 fenced block 없이 prose만 응답 → `_parse_response`가 raise → graceful 처리 없음 → 프로세스 crash.

### 1.2 영향

- e2e 측정 도중 crash → 결과 신뢰성 ↓ (재실행 비용)
- 운영 시 동일 → 사용자 입장에서 "엔진이 가끔 죽음" (운영 안정성 R12와 같은 결)
- LLM variance 분석 어려움

---

## 2. 해법 — `coder.run`에서 try/except + self-loop

`_parse_response`는 그대로 (exception purity). `run()` level에서 graceful 처리.

```python
fanout = max(1, int(state.get("coder_fanout") or 1))
temps = _temperatures(fanout)
candidates: list[dict[str, Any]] = []
parse_errors: list[str] = []
for temp in temps:
    chat_t = get_chat(CODER_MODEL, temperature=temp) if temp != 0.7 else chat
    resp = tracker.invoke(chat_t, messages, node="coder", state_calls=calls)
    try:
        c, b, imp, lsn = _parse_response(str(resp.content))
    except ValueError as e:
        parse_errors.append(f"temp={temp}: {e}")
        continue
    candidates.append({...})

if not candidates:
    return {
        **state,
        "llm_calls": calls,
        "feedback_message": (
            f"Coder response parse failed for all {fanout} fanout candidate(s): "
            f"{joined}. Wrap your solution in fenced python code block."
        ),
        "last_failed_node": "coder",
    }
```

### 2.1 fanout 활용

fanout=N이면 N candidate 중 일부만 fail해도 나머지는 그대로 채택. 모두 fail일 때만 self-loop. R14 fanout이 자연스러운 안전망 역할.

### 2.2 명확한 feedback

self-loop feedback에 "Wrap your solution in fenced python code block" 명시 → LLM이 다음 응답 시 fence 사용 가능성 ↑.

---

## 3. 변경 파일

| 파일 | 변경 |
|---|---|
| `ipe/nodes/coder.py` | `try/except ValueError` + 모든 candidate fail 시 self-loop |
| `tests/integration/test_coder_fanout.py` | `test_coder_self_loops_when_all_candidates_lack_fence` + `test_coder_proceeds_when_one_candidate_succeeds` |

---

## 4. 테스트 (+2)

| Test | 검증 |
|---|---|
| `test_coder_self_loops_when_all_candidates_lack_fence` | fanout=2 + 둘 다 fence 없음 → self-loop with feedback, no crash |
| `test_coder_proceeds_when_one_candidate_succeeds` | fanout=3, 1개만 valid → 그 candidate로 정상 진행 |

전체 회귀: **333 passed + 3 skipped** (Round 17의 331 + 본 PR +2).

---

## 5. 한계 + 후속

- **fenced block 형식 강제는 prompt-side**: 본 fix는 fail-safe (crash 방지). LLM이 fence를 항상 쓰도록 prompt 강화 (system message에 명시) 별도 가치.
- **다른 parse 오류는 별도**: `_parse_response`의 다른 ValueError (예: IMPOSSIBLE/LESSON parse 오류)는 현재 없음 (정규식이 optional). 향후 추가 검증 시 같은 패턴 적용 가능.
- **e2e variance는 별도 문제**: 본 fix는 crash 1종만 방지. SegTree variance (Round 17에서 success → fail) 같은 LLM quality 영향은 deterministic fix로 해결 어려움.
