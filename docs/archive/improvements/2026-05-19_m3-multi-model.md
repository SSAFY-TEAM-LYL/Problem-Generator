# M3 — Multi-Model Consensus (Architect Opus+Sonnet voting, v0.3.0 RFC PR #3)

**Date**: 2026-05-19 (Round 22)
**Scope**: v0.3.0 RFC §M3 구현 — ECC `Multi-perspective Analysis` 패턴을
Architect의 비결정성 완화에 적용
**Related**: CHANGES.md §28, `docs/rfc/v0.3.0_multi-mechanism.md` §2 M3

---

## 1. 동기

### 1.1 Architect 단일 모델 비결정성

기존 Architect는 Opus 한 모델로 1 호출. 같은 입력에도 cycle마다 응답 구조가
달라짐:
- 어떤 cycle은 `time_limit_ms=2000 / variables=2 / 3 samples`
- 다른 cycle은 `time_limit_ms=1000 / variables=3 / 5 samples`

이 흔들림이 downstream에 누적:
- Coder가 매번 다른 N 범위에 맞춰 IO 최적화 다시 해야 함
- Executor가 매번 다른 time_limit으로 측정 → oracle "slow" 오진단 가능
- Phase A sample expected가 모델 응답 시점마다 달라져 brute oracle cross-check
  변동성 ↑ (Round 19 R5에서 부분 완화했지만 근본 해결 X)

### 1.2 ECC Multi-perspective Analysis 패턴

ECC가 복잡 문제에 사용하는 패턴: 같은 task를 여러 viewpoint (factual reviewer /
senior engineer / security expert)에 동시 검토. 한 perspective의 편향을 다른
perspective가 상쇄.

IPE 적용: **Architect에 두 모델 family (Opus + Sonnet) 독립 호출** + 구조적 합의
검사. 둘 다 같은 구조를 도출하면 그 응답은 "한 모델 family 특유의 편향" 가능성이
낮아 신뢰도 ↑.

---

## 2. 설계

### 2.1 dual sequential call

```python
chat_opus = get_chat(ARCHITECT_MODEL, max_tokens=4096)     # claude-opus-4-7
chat_sonnet = get_chat(CONSENSUS_MODEL, max_tokens=4096)   # claude-sonnet-4-6

resp_opus = tracker.invoke(chat_opus, messages, node="architect", state_calls=calls)
resp_sonnet = tracker.invoke(chat_sonnet, messages, node="architect", state_calls=calls)
```

병렬이 아닌 **순차** 호출 — 이유 2가지:
1. `LLMCallTracker.seq` race 회피 (싱글 카운터에 동시 증분 시 lost-update)
2. trace 파일 순서가 호출 시점과 일치해야 후속 분석 일관

비용: 호출 2개 = latency 2×. 그러나 retry cycle 감소로 net cost는 ↓ 예상 (consensus
match로 첫 cycle에 정확한 구조 확정 시 downstream retry 없음).

### 2.2 `_parse_and_validate` — 공통 검증 helper

```python
def _parse_and_validate(content: str) -> tuple[dict[str, Any] | None, str | None]:
    """LLM 응답 1건을 parse + 형식 검증. (data, None) or (None, reason)."""
```

두 모델 호출 각각에 동일한 검증을 적용 (JSON parse / dict 여부 / required fields /
sample count ≥ 3 / constraints_structured 형식). 분기마다 try/except 복제하던
기존 코드를 1개 함수로 통합.

### 2.3 `_structural_match` — consensus 판정

```python
def _structural_match(a: dict, b: dict) -> bool:
    # 일치 조건 (모두 충족):
    # 1. constraints_structured.time_limit_ms 같음
    # 2. constraints_structured.memory_limit_mb 같음
    # 3. variables 개수 같음 + 정렬된 name 집합 같음
    # 4. sample_testcases 개수 같음
```

**비교하는 것**: 구조적 핵심 (time/memory/variable shape/sample count) — 두 모델이
"같은 문제"로 해석했다는 신호.

**비교하지 않는 것**: 제목/설명/sample 값 — 자연어 표현은 모델마다 달라도 정상.
오히려 자연어 다양성은 brittleness 회피에 도움.

### 2.4 5-way voting 결정

| 분기 | 조건 | 액션 | `architect_consensus` |
|---|---|---|---|
| 1 | 둘 다 invalid | `_route_back` (architect retry) | (없음) |
| 2 | Opus valid + Sonnet invalid | Opus 채택 (graceful) | `"opus_only"` |
| 3 | Opus invalid + Sonnet valid | Sonnet 채택 (graceful) | `"sonnet_only"` |
| 4 | 둘 다 valid + structural match | Opus 채택 (default) | `"match"` |
| 5 | 둘 다 valid + structural diff | `_route_back` (모호 신호) | (없음) |

분기 5 (둘 다 valid인데 구조 다름)가 핵심 신호: 문제 정의 자체가 모호하다는 뜻.
두 모델이 다른 해석으로 갈리면 retry feedback에 양쪽 구조 요약 포함 → 다음 cycle에
명세 강화.

### 2.5 state 신규 필드

```python
class ProblemState(TypedDict, total=False):
    ...
    # M3 (v0.3.0 RFC §M3) — Multi-model consensus for Architect.
    architect_candidates: list[dict[str, Any]]
    architect_consensus: str
```

`architect_candidates`: valid 응답만 저장 (1 or 2개). 분석/관측용 — 두 응답을
나중에 비교하면 모델별 편향 패턴 발견 가능.
`architect_consensus`: 어느 경로로 채택됐는지 표시. dashboard에서 시각화 가능.

---

## 3. ECC mapping

| ECC primitive | IPE M3 구현 |
|---|---|
| Multi-perspective Analysis | Opus + Sonnet 두 family 독립 호출 |
| Cross-validation | structural consensus → 둘 다 구조 동의해야 채택 |
| Graceful Degradation | 한쪽 fail 시 다른 모델 fallback |

---

## 4. 변경 파일

| 파일 | 변경 |
|---|---|
| `ipe/nodes/architect.py` | dual-call + `_parse_and_validate` + `_structural_match` + `_summarize` + 5-way voting |
| `ipe/llm.py` | `CONSENSUS_MODEL = "claude-sonnet-4-6"` 신규 |
| `ipe/state.py` | `architect_candidates` + `architect_consensus` field |
| `tests/test_architect_consensus.py` | 신규 unit tests (+23) |

`ipe/graph.py` 변경 **없음** — architect 노드만 내부 구현 교체. 외부 contract
(입력 → 출력 state shape) 동일.

---

## 5. 검증

### 5.1 단위 테스트 (+23)

- `TestParseAndValidate` ×6: success + 5 failure 분기 (parse / non-dict / missing
  field / too few samples / invalid constraints)
- `TestStructuralMatch` ×9: identical / title diff (match) / time diff / memory
  diff / variable count diff / variable name diff / variable order (match) /
  sample count diff / missing constraints
- `TestSummarize` ×2: structural fields / missing constraints handling
- `TestRunConsensus` ×6: match / opus_only / sonnet_only / both_invalid /
  structural_diff / 2 LLM calls 기록

### 5.2 회귀 0

전체 pytest: **401 passed + 3 skipped** (+23 신규, 회귀 0). ruff 0 / mypy --strict 0.

기존 architect mock 테스트 (`test_architect_unit.py`, `test_architect_phase_a.py`)
영향: lambda factory 패턴이 같은 mock chat을 2번 반환 → 둘 다 같은 응답 → match
consensus → 정상 path. **코드 변경 불필요.**

---

## 6. 후속 작업

### 6.1 M4 Adversarial review (다음 PR)

Solution → Reviewer gate. Coder가 작성한 solution을 별도 Reviewer 노드 (Opus
prompt: "이 솔루션의 약점/edge case 미처리를 찾아라")가 검토. 문제점 발견 시
coder retry feedback에 동봉.

### 6.2 v0.3.0 release (M4 후)

DoD: e2e 5 algorithm (Two Sum / BFS / Dijkstra / LIS / Segment Tree) × 3 run =
15 runs, 성공률 ≥ 80% (12+/15). 측정 후 v0.3.0 태그.

### 6.3 관측 plan

다음 e2e 측정 시 `architect_consensus` 분포 수집:
- match: 몇 %?
- opus_only / sonnet_only: 어느 모델이 더 자주 fail?
- 구조 diff retry: 얼마나 자주 발생? (잦으면 prompt 모호도 신호)

이 데이터로 M3가 실제 신뢰성 향상에 기여했는지 정량 검증 가능.
