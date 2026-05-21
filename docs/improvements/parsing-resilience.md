# Parsing Resilience — Coder fenced block + LLM 응답 graceful fallback

**Last updated**: 2026-05-21
**Scope**: LLM 응답 format 변동 (펜스 누락, JSON 안 markdown ``` 등) 에 의한
parse crash 차단.
**Status**: 운영 중.

원본 RCA 는 [`docs/archive/improvements/`](../archive/improvements/) 에 보존.

---

## 0. 개요

LLM 응답 형식이 prompt 와 다를 때 (펜스 누락 / 추가 markdown ``` 포함 / non-dict
JSON) crash 가 발생해 IPE run 전체 중단. R-coder-parse (Round 18) 는 그 중
첫 fix. baseline runner (v0.3.0) 도 같은 패턴으로 brace-balanced JSON parser
도입.

---

## 1. 포함된 fix

| Round | Fix | 원본 RCA | 영향 |
|---|---|---|---|
| 18 | R-coder-parse | [`2026-05-19_coder-parse-fallback.md`](../archive/improvements/2026-05-19_coder-parse-fallback.md) | Coder 응답 펜스 누락 → coder self-loop |
| v0.3.0 | brace-balanced JSON parser (baseline) | (이 PR 의 SPEC.md §4.4 + `ipe/baseline/runner.py`) | JSON 안 markdown ``` 펜스 graceful |

---

## 2. 패턴

### 2.1 Coder fenced block 누락 (Round 18)

증상: Round 16 BFS variance run 에서 LLM 이 ` ```python ... ``` ` 없이 답 →
`_parse_response` 에서 `ValueError` raise → graph 전체 crash.

원인: LLM 응답 형식이 prompt 와 다름. retry 로 회복 가능한 noise 인데 crash 가
회복 기회를 막음.

Fix: `_parse_response` 의 `ValueError` 를 try/except 로 잡아 coder self-loop
+ explicit feedback. fanout candidate 중 일부만 fail 해도 나머지로 진행.

### 2.2 baseline brace-balanced JSON parser (v0.3.0)

증상: `python -m ipe.baseline batch` 첫 실행 (2026-05-20) — Two Sum / BFS /
Dijkstra 모두 `unparseable`. raw 응답 보면 json 펜스 안에 problem_description
의 input/output 예시가 markdown ``` 으로 들어있어 non-greedy fence match 가
거기서 잘림.

Fix: `_extract_json_balanced(content)` — ```json 펜스 시작 위치 찾고, 그 직후
`{` 부터 brace count 0 으로 돌아오는 곳까지 raw JSON parse. 문자열 내부 ``` 은
brace count 영향 X.

재측정 후 5 algorithm 중 2 success — fix 자체가 measurement 의 정확성을 가렸음.

---

## 3. 측정 데이터

- Round 18 이전: BFS variance run 에서 fenced block 누락 1 회 crash 발생 →
  graph 전체 중단
- Round 18 이후: 같은 패턴이 coder self-loop 으로 처리 + feedback 으로 회복 가능
- baseline N=3: brace-balanced parser 도입 후 `unparseable` 0건 (이전엔 3/5)

---

## 4. Rollback trigger (PRINCIPLES.md 룰 5)

- R-coder-parse: fenced block 누락이 N=3 측정에서 0건 발생하면 → LLM prompt 가
  안정적이라는 신호. fix 유지 (crash 차단은 cheap insurance).
- brace-balanced parser: JSON 안 markdown ``` 패턴이 N=3 측정에서 0건 발생하면
  → 단순 non-greedy fence 로 회귀 검토.

---

## 5. 후속 개선 후보

- baseline runner 의 brace-balanced parser 를 `ipe/llm.py:parse_json_block` 의
  fall-through 로 통합 → IPE 전체 노드 (architect / coder / reviewer 등) 의 JSON
  parser 동일 개선.
- LLM prompt 에서 problem_description 안에 ``` 사용 금지 명시 (parser-side fix
  vs prompt-side fix 의 trade-off).
