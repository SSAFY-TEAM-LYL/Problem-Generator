# IPE 전략 리뷰 — 길을 잃지 않기 위한 정직한 진단

> **⏳ 한시 문서 (archived)**: 본 보고서는 2026-05-21 시점의 진단. 권고 액션
> (cruft 청소 / SSOT 통합 / M3 rollback 등) 실행 완료 후 archive 로 이동됨.
> 현 상태는 `docs/SPEC.md` + `docs/PRINCIPLES.md` + `docs/ARCHITECTURE.md` 가
> 최신 SSOT.

**Date**: 2026-05-21
**Branch at write**: `analysis/n3-wider-data`
**Main HEAD**: `ab50bd7` (PR #71 머지 — N=3 baseline 측정)
**Status**: 외부 시각으로 작성한 진단 보고서 — 의사결정용 SSOT

> 이 문서는 "Round 11~23 + M1~M4 + Catalog + PRINCIPLES + Baseline" 의 누적 변경 후
> 어디에 와 있고, 무엇이 길을 잃게 만들었고, 무엇을 살려야 하고, 다음 한 발을
> 어디로 디뎌야 하는지를 정리한다.

---

## 0. TL;DR — 한 화면

- **IPE 의 핵심 가설("multi-mechanism → e2e quality ↑")은 측정으로 부분 반박됨.**
  N=3 데이터 (`docs/baseline/v0.3.0-rc1-N3.md`): IPE **3/15 (20%)** vs 단일 Opus baseline
  **4/15 (27%)**. run-level **-7pp**, sample-level **+9pp**. 즉 IPE 는 "오류를 더
  잘 찾되, 더 못 복구함".

- **M3 multi-model consensus 는 명백히 음효과.** Dijkstra baseline **3/3 → IPE
  0/3**. PRINCIPLES.md 룰 2 (cross-algorithm regression) 의 실제 사례. v0.3.0
  tag 가 보류된 결정적 이유.

- **그러나 IPE 의 *진짜* 가치는 generation quality 가 아니라 verification +
  catalog + observability layer.** Phase B/C / Replay / Catalog / Sandbox / LLM
  traces — 이 영역은 baseline 비교 영역 밖이며, 단일 LLM call 로는 제공 불가.

- **누적 부산물이 위험 수준.** `outputs/` **2.6 GB / 105 runs**, `workdir/` **2.2
  MB stale**, **25+ git branches** (대부분 머지된 feature/*), **CHANGES.md 2200
  줄 / 33 sections**, **18 RCA 문서**. fix 1건마다 RCA 1건 + branch 1개 + outputs
  N개가 쌓이는 구조.

- **다음 한 발의 정답은 "더하기 PR" 이 아니다.** PRINCIPLES.md 룰 4 (complexity
  budget) 가 이미 cap 임박 (7 nodes / 10 safety vs cap 8 / 12). 추가하려면 빼야
  한다. 우선순위: **M3 rollback A/B → narrative 재정의 → cruft 청소 → release
  DoD 재정의**.

---

## 1. 지금 어디 와 있나 — 사실관계만

### 1.1 측정 데이터 (가장 중요)

`docs/baseline/v0.3.0-rc1-N3.md` (2026-05-21) 의 핵심 표:

| Algorithm | baseline N=3 | IPE N=3 |
|---|---|---|
| Two Sum | 1/3 | 1/3 |
| BFS | 0/3 | 0/3 |
| **Dijkstra** | **3/3** | **0/3** ← M3 음효과 |
| LIS | 0/3 | 0/3 |
| Segment Tree | 0/3 | 2/3 |
| **Run-level total** | **4/15 (27%)** | **3/15 (20%)** |
| **Sample-level pass** | **78.7%** | **87.7%** |

- v0.3.0 RFC 의 DoD: **e2e success ≥ 80%** (12/15) — **달성 못 함** (3/15).
- baseline ≈ IPE band (`|Δ run| < 20pp`) → PRINCIPLES.md §3 결정 트리상 **"IPE 는
  검증 layer 만 정당화"** 시나리오.

### 1.2 코드 형태

`find ipe -name "*.py" | wc -l = 6,418 LOC` (테스트 8,230 LOC 별도).

| 파일 | LOC | 비고 |
|---|---|---|
| `ipe/nodes/_executor_phases.py` | **576** | Phase B/C 본체 — 가장 무거움 |
| `ipe/nodes/executor.py` | 447 | 3-Phase 오케스트레이션 |
| `ipe/observability.py` | 323 | LLMCallTracker / ReplayTracker / pricing |
| `ipe/nodes/architect.py` | 314 | M3 dual-call 포함 |
| `ipe/graph.py` | 310 | 라우팅 + oscillation swap + reviewer cond |
| `ipe/nodes/generator.py` | 302 | seed-based generators |
| `ipe/baseline/runner.py` | 282 | 신규 — N=3 측정용 |
| `ipe/nodes/coder.py` | 277 | M1 이후 implementer 측 |
| `ipe/nodes/reviewer.py` | 261 | M4 신규 |

`ProblemState` (`ipe/state.py:69`) 는 **30+ 필드** — Architect output, M1 designer,
M3 candidates, M4 review, Coder output, Auditor, Generator, Executor, Iteration,
Evaluator. god-dict 임계 근처.

그래프 토폴로지 (`ipe/graph.py:278~`):

```
architect → algorithm_designer → coder → reviewer ─┬─ executor
                                                   └─ decision (reject)

executor → decision → {architect | algorithm_designer | coder | auditor |
                       generator | evaluator | END}
```

- **노드 7** (architect, algorithm_designer, coder, reviewer, auditor, generator,
  evaluator) — 룰 4 cap 8 까지 **남은 칸 1**.
- **safety mechanism 10** (R-osc-break, R-gen-cap, R-coder-osc, R-sig-detail,
  R-phase-a-osc-break, R-coder-parse, R5 brute oracle, M2 hooks, M3 dual-call,
  M4 reviewer) — 룰 4 cap 12 까지 **남은 칸 2**.

### 1.3 누적 부산물

| 항목 | 크기 / 개수 |
|---|---|
| `outputs/` | **2.6 GB / 105 run 디렉토리** |
| `workdir/` | 2.2 MB stale sandbox temp |
| git branches (local) | **25개** — main 외 24개 중 머지 후 미삭제 다수 |
| `CHANGES.md` | **2,200 줄 / 33 sections** (Round 1~23 + RFC + M1~4 + catalog + principles + baseline) |
| `docs/improvements/*.md` | **18 RCA** (Round 11~23 각각 + M1~4 + r5 + phase-a 등) |
| `docs/backlog/*.md` | 8 (post-P3~P12) |
| `docs/baseline/` | 2 measurement docs + raw data |
| root `*.md` | 6 (README / ONBOARDING / REQUIREMENTS / TECH_STACK / CHANGES / aa) |
| `docs/dev/*.md` | 4 SSOT 문서 (PROJECT_SPEC / ARCHITECTURE / ROADMAP / PYTHON_GUIDE) |
| `docs/site/` | HTML 대시보드 + assets/data.js |

### 1.4 narrative — 문서가 말하는 것 vs 측정이 말하는 것

`README.md:18`:
> "외부 문제 소스에 의존하지 않고 **고품질** 알고리즘 문제(SWEA B형, 백준 골드
> 수준 포함)를 **자체 생산**하는 파이프라인이다."

`README.md:5~7` badge:
> `v0.2.1-brightgreen` · `tests-247 passed` · `e2e-4/5 success-brightgreen` ·
> `coverage-93%`

`docs/baseline/v0.3.0-rc1-N3.md`:
> "**판정**: v0.3.0 tag 보류 + multi-mechanism 일부 rollback 검토 PR."
> "run-level: baseline 27% > IPE 20%"

→ README 가 가리키는 상태(v0.2.1 / e2e 4/5)와 실제 release-candidate 측정 결과
사이에 **2주치 갭**이 있음. 외부에서 보면 "고품질 자체 생산" 클레임이 데이터로
backing 되지 않은 상태.

### 1.5 aa.md — team coordination 신호

`aa.md` (root, 4 줄):
```
해논거 공유
인당 태스크 분배 가능하면 ㄱㄱ
요구사항정의서
pt는 b2c로
```

→ B2C presentation 단계 준비 중이라는 신호. 그러나 위 1.1 데이터 기준으로
**현재 narrative ("고품질 문제 자체 생산")는 PT slide 에 못 올림** (baseline
대비 quality 우위 입증 X). PT 를 위한 메시지 재정의가 필요.

---

## 2. 진짜 문제 진단 — 5가지

### 2.1 [Strategic] quality 목표와 측정 결과의 갭

- v0.3.0 RFC DoD: **80% e2e success**. 실측 **20%**.
- v0.2.0 시점 README: "e2e 4/5 stable" — N=1 측정 기반. 룰 1 (N≥3) 적용 후 같은
  anchor 가 더 낮은 점수로 재측정될 가능성.
- **목표 자체가 LLM stochasticity 한계 너머일 가능성.** baseline 4/15 = 단일
  Opus 의 천장. 이 천장이 60% 가까이 가지 못한다면, IPE pipeline 이 천장을 +20pp
  넘는 것은 architectural 변화 (예: domain-specific skill library, RAG,
  fine-tuning) 없이는 불가능.
- **결론**: DoD 를 60% 또는 "검증 후 catalog 적재 수" 같은 *operational* metric
  으로 재정의해야 자기기만 없이 release 판정 가능.

### 2.2 [Architectural] detection 효과는 있지만 recovery 미달

- IPE sample-level pass **+9pp** = Phase A sample mismatch 로 wrong sample 발견
  잘 함.
- IPE run-level **-7pp** = 발견했지만 budget 안에 fix 못함.
- Baseline N=3 의 failure mode: `wrong_sample` (76%) — LLM 이 expected 를 자기
  솔루션 mental-sim 으로 적다 틀림.
- IPE N=3 의 failure mode: `budget_exhausted` (93%) — 검증으로 wrong 잡고 coder
  retry, 같은 algorithm misunderstanding 반복하다 budget 소진.

→ **multi-stage verification 이 더 strict 해지는 만큼 recovery 에 쓸 budget
이 줄어든다.** detection cost 가 recovery budget 을 잠식. "더 잡고 못 고침"
trade-off.

가능한 대응:
- **(A)** budget cap 을 늘림 — coder 4 → 8, max_iter 5 → 10. cost 2-3× ↑.
- **(B)** detection 을 더 *cheap* 하게 — R5 brute oracle 처럼 LLM 없는 결정적
  cross-check 만 의지, M3/M4 같은 LLM-additional verification 줄임.
- **(C)** recovery 전략을 LLM call 외부에서 — algorithm-specific skill library
  (BFS 어떻게 짜는지 정해진 reference), 또는 simple problem ↔ algorithm rerouting.

### 2.3 [Mechanism] M3 multi-model 의 명백한 음효과

`docs/baseline/v0.3.0-rc1-N3.md` §4.3:

| Algorithm | baseline | IPE | Δ |
|---|---|---|---|
| Dijkstra | **3/3** | **0/3** | **-100%** |

원인 패턴: IPE r3 Dijkstra 에서 **architect 0-iter**. M3 dual-call (Opus +
Sonnet) 이 둘 다 valid 응답인데 structural diff 가 발생 → consensus 실패 →
architect budget 빠르게 소진.

- Dijkstra 는 baseline 이 100% 푸는 단순 잘 정의된 문제. 즉 단일 LLM 이
  hallucination 없이 처리할 수 있는 도메인.
- M3 의 voting 이 그 도메인까지 *깎아먹는다*.
- M3 의 net effect: **잘 정의된 algorithm 에 -, 어려운 algorithm 에 효과 측정
  안 됨**.

PRINCIPLES.md 룰 2 (cross-algorithm regression check) 의 교과서적 사례. M3 도입
PR (`Round 22`) 이 룰 2 적용 전이라 잡지 못했음.

**권고**: M3 rollback PR — single Opus architect 로 복귀. A/B 측정으로 net
effect 정량화 후 본 머지.

### 2.4 [Operational] cruft 누적

#### 2.4.1 `outputs/` 의 무거움

- **2.6 GB / 105 run 디렉토리**. 한 run 당 평균 ~25 MB (LLM traces + checkpoint.db
  + workdir generators + tests). gitignored 라 repo size 영향은 X 이나, local
  disk + grep speed + IDE indexing 부담.
- 디렉토리명이 `<run_id>` hex 12자라 사람이 식별 불가. `outputs/by-name/...`
  symlink 가 일부 도와주지만 105 개 중 catalog 에 promote 된 것은 3 개
  (`docs/baseline/v0.3.0-rc1-N3.md` §6).
- **102 개의 일회용 run** — 측정 데이터로 추출 후 보존 가치 없음. 그러나 GC
  정책 없음.

#### 2.4.2 `workdir/` — sandbox temp 쓰레기

- `run_<hex>/tmp<hex>/` 형식 다수. sandbox 종료 후 cleanup 누락.
- 2.2 MB 이지만 디렉토리 inode 수천 개 — `find` / `ls` 가 느려짐.

#### 2.4.3 git branches

- local 25개 / origin 동일 수준. main 외 24개 중 머지 후 미삭제 대다수.
- branch graph 가 시각적으로 노이즈 — 어느 게 active 인지 모름.
- `analysis/n3-wider-data` 같은 분석 brench 가 main 머지 의도 없이 누적.

#### 2.4.4 RCA 문서 fragmentation

- `docs/improvements/` 에 fix 1건당 1 RCA. 총 18개.
- 패턴이 비슷한 RCA 끼리 묶이지 않아 새 fix 시 "비슷한 fix 가 있었나?" 찾기
  힘듦.
- 예: `R-osc-break` / `R-coder-osc` / `R-phase-a-osc-break` — 모두 oscillation
  관련이지만 3 RCA 가 별도. "Oscillation Breakers" 한 RCA 로 통합 + 각 round 의
  delta 만 기록 가능.

#### 2.4.5 documentation sprawl

| 위치 | 파일 | 줄 수 | 역할 |
|---|---|---|---|
| root | README.md | 208 | 진입점 |
| root | REQUIREMENTS.md | 407 | 제출용 요구사항 |
| root | TECH_STACK.md | 348 | 제출용 기술 스택 |
| root | CHANGES.md | **2,200** | 변경 이력 |
| root | ONBOARDING.md | 552 | 처음 보는 사람 가이드 |
| root | aa.md | 4 | scratch — 정리 필요 |
| docs/ | PRINCIPLES.md | 194 | 운영 정책 SSOT |
| docs/dev/ | PROJECT_SPEC.md | (264 추정) | 기술 SSOT |
| docs/dev/ | ARCHITECTURE.md | (1081 추정) | 모듈 설계 |
| docs/dev/ | IMPLEMENTATION_ROADMAP.md | ? | phase 로드맵 |
| docs/dev/ | PYTHON_GUIDE.md | ? | 문법 참고 |

- **CHANGES.md 2,200 줄**. 한 PR 머지 시마다 추가되는 구조 → 1년이면 6000줄+.
- **README badge 에 v0.2.1 / e2e 4/5** — 2026-05-19 마지막 update. 2026-05-21
  baseline N=3 결과 미반영. PT 자료 만들 때 외부인이 README 만 보면 outdated
  narrative 를 그대로 들고 감.
- 신규 onboarding 문서가 6 위치에 분산. "어디부터 읽나" 가 사람마다 다름.

### 2.5 [Product] narrative ↔ value 의 mismatch

README 의 promise: "외부 문제 소스 없이 고품질 알고리즘 문제 자체 생산".

baseline N=3 의 정직한 해석:
- IPE 의 **generation 부분** (architect → designer → coder) 은 단일 Opus 보다
  나쁨 (run-level -7pp).
- IPE 의 **verification 부분** (Phase B/C + Reviewer + Hooks + Brute oracle)
  과 **operational 부분** (Replay / LLM traces / Sandbox 4-tier / Catalog) 은
  단일 Opus 가 제공 불가.

즉 **IPE 의 진짜 product 는 "검증된 문제의 audit-able 저장소"** 이지, "더 잘
생성하는 엔진" 이 아니다. PRINCIPLES.md §3 도 같은 결론에 도달함:
> "baseline ≈ IPE → IPE 는 검증 layer 로만 정당화 (Catalog / Replay / Phase B/C)."

→ B2C PT 의 hook 을 "고품질 자체 생산" 에서 **"검증된 문제 + 사람 review-able
catalog + 재현 가능 trace + sandbox 격리"** 로 재정의 필요. 이는 cosmetic 변경이
아니라 product positioning 의 전환.

---

## 3. 강점 — 다행히 안 잃은 것

분해와 재정의 과정에서 *지키고 두 배 베팅해야* 할 것들.

### 3.1 PRINCIPLES.md + measurement gate (2026-05-20 도입)

- **룰 1 (N≥3)** — 이번 baseline N=3 측정이 정확히 이걸로 시작. 룰 없었으면
  M3 의 음효과를 발견 못 했을 것.
- **룰 2 (cross-algorithm regression)** — Dijkstra 0/3 사례를 *문서적으로 측정
  의무화*. 룰 4 (complexity budget) 가 무한 누적 차단.
- **룰 5 (RCA rollback trigger)** — RCA 가 dead-letter 가 되지 않게 보장.

**평가**: 이 5 룰은 IPE 의 *가장 가치 있는 최근 변경*. multi-mechanism 보다 더.
이 룰 없었으면 Round 24~30 으로 같은 패턴 반복했을 것.

### 3.2 verification layer — IPE 만의 가치

- **Phase B (adversarial)** — Auditor 가 만든 corner case. baseline 비교 영역
  밖이지만 단일 LLM call 로는 제공 불가.
- **Phase C (stress)** — seed 기반 generator. testcase 자동 생성 + golden vs
  brute cross-check. competitive programming 문제의 핵심 가치 (백준 호환
  포맷).
- **Brute oracle (R5)** — Phase A sample-wrong 결정적 차단. LLM 노이즈 외부의
  결정적 신호.

→ 다음 release 의 narrative 가 *여기* 에 있어야 함.

### 3.3 observability — audit-able pipeline

- **LLM traces** — `outputs/<run_id>/llm_traces/<seq>_<node>.json`. 모든 input/
  output raw 저장. cost ↑, debugging ↓.
- **Replay mode** — `ipe --replay <run_id>` LLM 비용 0 으로 동일 run 재현.
- **`emit_metric()` + LangSmith / OTel** — 옵션 토글로 외부 관측성 통합.

→ Anthropic API 청구 추적 / debugging / 회귀 테스트 / 사후 감사 4가지 use case.

### 3.4 sandbox 4-tier — 진짜 security 작업

- T1 Docker (`--network=none --read-only`) → T2.5 sandbox-exec (macOS) → T3
  rlimit fallback.
- `make selftest-all` 격리 자가진단.
- **LLM 코드를 host 에서 직접 실행 안 함** — supply chain 보안 우려를 architectural
  으로 차단.

→ 외부 review 시 가장 인상적 강점. LLM ecosystem 의 대부분이 이걸 skip.

### 3.5 catalog persistence (2026-05-20 도입)

- `outputs/catalog/problems.jsonl` — success run 만 promote.
- 사람 review 가능 상태로 저장.
- → **IPE 의 진짜 output unit 은 "1 run 의 성공/실패" 가 아니라 "catalog 에
  promote 된 문제의 누적"**.

→ release DoD 를 "e2e 80% success" 에서 "catalog 에 50문제 promote" 같은 *누적*
metric 으로 바꾸면, stochasticity 와 무관하게 가치 측정 가능.

### 3.6 baseline measurement 인프라 (2026-05-20)

- `ipe/baseline/runner.py` (282 LOC) — 단일 Opus call 측정 모듈 + CLI.
- N=3 데이터 raw JSONL 보존.
- → 매 release 마다 재측정 가능, regression detection 의 토대.

---

## 4. 취약점 — 깊은 위험

### 4.1 [Structural] information bottleneck (PRINCIPLES.md §1.2)

- 노드 간 통신이 **자연어 + JSON** — 모든 node-to-node 정보가 LLM 응답을 거쳐
  변환됨.
- 매 노드 추가는 정보 loss 1 단계 추가. M1 (Designer) 도입 후 Coder 가
  algorithm.json 만 보고 implementation — original problem 의 nuance 일부 손실
  가능.
- M3 dual-call → consensus voting → "둘 다 valid 인데 sample format 다르면
  reject" — 정보 평면화.

**대응 후보**:
- 노드 간 통신을 **structured field** 로 - free-form JSON 대신 strict schema.
  현재 `ipe/state.py:ConstraintSpec` 이 시작점.
- LLM call 외 deterministic transformer 추가 (예: constraint parser,
  validator).

### 4.2 [Operational] complexity budget cap 임박

PRINCIPLES.md 룰 4 (`docs/PRINCIPLES.md:108~`):
> "그래프 노드 ≤ 8, safety mechanism ≤ 12. 추가하려면 기존 1개 simplify 또는 remove."

현재: **7 nodes / 10 safety**. 다음 PR 에서 무엇이든 추가하려면 기존 1개 제거가
조건.

후보 mechanism 제거:
1. **M3 (multi-model)** — 측정 데이터로 음효과 입증. 명확한 1번 후보.
2. **M4 (reviewer)** — net effect 측정 어려움. 단독 A/B 필요.
3. **R-coder-osc + R-phase-a-osc-break** — oscillation breaker 3종 통합 후보.

### 4.3 [Code] ProblemState god-dict / executor 복잡도

- `ipe/state.py:69` 의 `ProblemState` 가 30+ field.
- 각 노드는 일부만 read/write 하지만 type system 으로는 구분 불가 (`total=False`
  TypedDict).
- M5/M6 추가 시 더 늘어남.

**대응**:
- 노드별 **input/output protocol** 정의. e.g. `ArchitectOutput`,
  `CoderInput`, `ExecutorContext`. ProblemState 는 union/composition.
- `_executor_phases.py` (576 LOC) 를 Phase A / B / C 별 모듈 분리.

### 4.4 [Data Governance] outputs/ 의 무거움

- 2.6GB, 105 runs. GC 정책 없음.
- catalog promote 된 3 runs 외 102 runs 는 일회용.
- LLM traces 가 cumulative cost — replay 가치는 있지만 모든 run 에 다 필요한가?

**대응**:
- `outputs/` retention policy: catalog promote / 최근 N 일 / 측정 anchor 만 보존.
- 나머지는 `archive/runs/<YYYY-MM>/` 로 압축 후 이동.
- 또는 `outputs/.keep` manifest 로 명시적 보존 표시.

### 4.5 [Cost] single Opus 의존 비용 vs 가치 ratio

- baseline N=3: ~$0.75 / 15 runs.
- IPE N=3: 별도 측정 안 되었으나 architect + designer + coder + reviewer +
  auditor + generator × multiple LLM calls × 15 runs → **추정 $15-30**.
- run 당 cost ratio: IPE / baseline ≈ **20-40×** for **-7pp** run-level.
- success run 당 effective cost: IPE 5 success × ~$2 = $10/success vs baseline
  4 success × $0.05 = **$200×** 차이는 너무 큼.

**대응**:
- Architect 만 Opus, 나머지 노드는 Sonnet 4.6 (PRINCIPLES.md §1 성능 모델
  선택).
- M3 rollback 으로 Architect call 도 1회로.
- Reviewer (M4) 가 정말 net positive 인지 단독 A/B.

### 4.6 [Process] PR 후 measurement N=3 의 비용

룰 1 (N≥3) + 룰 2 (cross-algo) 적용 후 매 PR 마다 5 algo × 3 run = 15 run 측정.

- 1 PR 측정 시간: 알고리즘별 ~5분, 15 run 직렬 = 1.5시간. Anthropic API 529 등
  포함 시 2-3시간.
- cost: $15-30 / PR.
- 이 비용 자체가 PR throughput 을 cap. **process 가 product 보다 비싸짐**.

**대응**:
- PR scope 를 작게 묶기 (R-osc-break + R-coder-osc 같이 친밀한 fix 를 1 PR
  로).
- 측정 자동화 — `make measure-all` 같은 makefile target. PR 머지 후 즉시
  background 측정 + 결과만 PR comment.
- 측정 anchor 축소 (2 algo × 3 run = 6 run) — speed/cost trade.

### 4.7 [Reproducibility] LLM response variance 자체의 한계

- 같은 algorithm × 3 run 에서 fail mode 가 매번 다름 (BFS r1 coder, r2
  architect, r3 generator).
- "fix" 는 *모드별 fix* 가 아니라 *모드 분포 자체*를 바꿔야 함.
- 그러나 모드 분포는 LLM 의 내재적 stochasticity → architectural change (RAG,
  skill library) 없이는 분포 shift 불가.

**대응 (구조적)**:
- **skill library** (`ipe/skills/algorithms/{bfs,dijkstra,...}.md`) — 알고리즘
  별 reference implementation + 자주 틀리는 pattern. Coder 가 prompt 에 포함.
  ECC `skills/` 패턴의 IPE 적용.
- 또는 baseline 의 단일 Opus call 을 **fixed** quality 천장으로 받아들이고,
  IPE 의 가치를 verification + catalog 로 재정의 (§5 참고).

---

## 5. 권고 — 우선순위 액션

### 5.1 즉시 (이번 주, 1-3 일)

**[P0] M3 rollback A/B 측정 PR**
- `feat/v0.3.0-m3-rollback-ab` branch.
- `ipe/nodes/architect.py` 의 dual-call 을 flag (`--architect-multi-model
  bool`) 로 toggle 가능하게.
- 5 algo × 3 run × {with-M3, without-M3} = 30 run 측정.
- 결과: without-M3 ≥ with-M3 → M3 rollback PR 머지. 룰 4 budget +1 회수.
- 산출물: `docs/baseline/v0.3.0-rc2_m3-ab.md`.

**[P0] README badge 동기화 + narrative 일치화**
- Badge `v0.2.1` → `v0.3.0-rc1` 또는 `v0.3.0-rc1 (release held)`.
- Badge `e2e-4/5` → `e2e-3/15 N=3` 또는 제거.
- README §개요: "고품질 자체 생산" → "검증된 알고리즘 문제 + audit-able catalog"
  로 재정의 (§2.5 참고).
- Status 표: v0.3.0 행 추가, "tag held — multi-mechanism A/B 측정 중" 표시.

**[P1] aa.md 정리**
- 내용 (해논거 공유 / PT B2C) 을 `docs/discussions/2026-05-21_pt-prep.md` 또는
  유사 위치로 이동, root 에서 제거.
- PT 메시지 초안 작성 — §3 의 강점 (verification + observability + catalog +
  sandbox) 을 hook 으로.

### 5.2 단기 (1-2 주)

**[P0] release DoD 재정의**
- 현 DoD ("e2e 80%") 는 LLM 천장 너머 → **현실적 metric 으로**:
  - **option A**: e2e ≥ 50% (baseline 27% 의 ~2× — 검증 layer 가치 반영).
  - **option B**: "catalog 에 promote 된 problem 수 / 측정 N" — quality 누적.
  - **option C**: "sample-level pass ≥ 85% + run-level ≥ 30%" — 다층 metric.
- PRINCIPLES.md §3 update 동반.

**[P0] cruft 청소 — outputs / branches / workdir**
- `outputs/` retention: catalog promote / 최근 7 일 / baseline N=3 anchor 만 보존.
  나머지 `archive/runs/2026-05/` 로 이동 + `.tar.gz`.
- workdir/ 전체 삭제 후 .gitignore 확인.
- 머지 완료된 feature/* / fix/* branch 일괄 삭제 (local + origin):
  ```bash
  git for-each-ref --format='%(refname:short)' refs/heads/ \
    | grep -vE '^(main|analysis/)' \
    | xargs -I {} git branch -d {} 2>/dev/null
  ```
  (force-delete 는 user 확인 후)

**[P1] RCA consolidation**
- `docs/improvements/oscillation-breakers.md` 통합 — R-osc-break +
  R-coder-osc + R-phase-a-osc-break 한 문서로.
- 비슷한 패턴 RCA 끼리 통합: `docker-infra.md` (workdir + mount),
  `parsing-resilience.md` (coder-parse + sig-detail), `retry-resilience.md`
  (R12 + cost guard).
- 통합 후 18개 → ~8개 RCA.

**[P1] PT 자료 작성 (3.6 강점 중심)**
- Slide 1: 무엇 — "검증된 알고리즘 문제 + 사람 review-able catalog".
- Slide 2: 왜 — 크롤링 risk + 사람 출제 cost + 검증 안 된 LLM 출력의 risk.
- Slide 3: 어떻게 — 4-tier sandbox + Phase A/B/C verification + Catalog
  promote.
- Slide 4: 비교 — vs 단일 LLM (sample-level +9pp) + vs 외부 사이트 (compliance
  ✓).
- Slide 5: 측정 — baseline measurement + Replay + LLM traces (audit-ability).

### 5.3 중기 (3-4 주)

**[P1] skill library 도입 (M5 후보)**
- `ipe/skills/algorithms/{bfs,dijkstra,segment-tree,...}.md` — algorithm
  reference implementation + 자주 틀리는 pattern.
- Coder prompt 에 target_algorithm 매칭 skill 동봉.
- 회귀 risk 측정: baseline N=3 재측정.
- **M5 추가 = 기존 1개 제거 (룰 4)** — M3 rollback 후 빈 자리에 들어감.

**[P2] coder.py / executor.py 분해**
- `ipe/nodes/coder.py` 277 LOC → `coder/implementer.py` + `coder/brute.py` 분리.
- `ipe/nodes/_executor_phases.py` 576 LOC → `_phase_a.py` + `_phase_b.py` +
  `_phase_c.py` 분리.
- 회귀 0 보장, mypy --strict 통과 유지.

**[P2] catalog UI / review workflow**
- `outputs/catalog/problems.jsonl` 을 사람이 review 가능한 형태 (Markdown index,
  HTML preview).
- 현재 docs/site/ 인프라 활용.
- B2C PT 의 *demonstration object*.

---

## 6. v0.3.0 release 판정 — 데이터 기반 결정 트리

PRINCIPLES.md §3 + 현 데이터:

| 시나리오 | 측정 데이터 (현재) | 권고 |
|---|---|---|
| baseline ≫ IPE | Δ run -7pp / sample +9pp → 중간 zone | M3 rollback A/B 우선 |
| baseline ≈ IPE | **현 상태 (band 내)** | **release 판정**: |
| | | 1. v0.3.0-rc1 narrative 재정의 (verification layer 가치) |
| | | 2. DoD 재정의 (catalog 누적 또는 run-level 30%) |
| | | 3. M3 rollback 후 재측정 |
| | | 4. 통과 시 v0.3.0 tag |
| baseline ≪ IPE | — | (해당 없음) |

### 6.1 next-PR 결정 트리

```
M3 rollback A/B 측정 (5 algo × 3 run × 2 = 30 run)
   │
   ├── without-M3 > with-M3 (Δ > +5pp run-level)
   │     → M3 rollback PR 머지 → 룰 4 budget +1 회수
   │     → 다음: skill library (M5) PR (M3 자리)
   │
   ├── without-M3 ≈ with-M3 (|Δ| ≤ 5pp)
   │     → M3 rollback 머지 (cost 절약만으로 가치)
   │
   └── without-M3 < with-M3 (Δ < -5pp)
         → M3 유지 + 다른 분석 (의외 결과)
```

---

## 7. 길을 잃지 않기 위한 가이드 — 이 문서를 어떻게 쓸까

### 7.1 어떤 PR 도입 전 self-check 7가지

1. [ ] 이 PR 이 *생성 quality* 를 올리려는 것인가, *검증/관측 layer* 를 더하는
   것인가? 후자라면 §3 강점 강화 — 강력한 후보.
2. [ ] 측정 anchor (BFS, Dijkstra, LIS, Segment Tree, Two Sum) 중 어느 algorithm
   의 fail 을 fix 하나? 그 fail 이 N≥2 에서 재현되었나? (룰 1)
3. [ ] 5 algorithm 다 측정해서 regression 없는 것 확인했나? (룰 2)
4. [ ] 새 노드/safety 추가면 기존 1개 simplify 또는 remove 계획 있나? (룰 4)
5. [ ] RCA 에 rollback trigger 명시했나? (룰 5)
6. [ ] PR scope 가 1주 measurement budget ($15-30, 1.5-3 시간) 안에 들어오나?
7. [ ] 이 PR 이 README narrative 와 일치하나? 안 일치하면 README 도 같이 update.

### 7.2 매 release 의 DoD checklist

- [ ] baseline N=3 측정 갱신 (`docs/baseline/<version>.md`)
- [ ] IPE N=3 측정 갱신 (같은 anchor)
- [ ] 비교 표 작성 + § 판정 (PRINCIPLES.md §3 결정 트리)
- [ ] README badge / status 표 update
- [ ] CHANGES.md section 추가
- [ ] catalog promote 수 명시
- [ ] cruft 청소 — outputs/ retention, branches GC, RCA consolidation

### 7.3 외부 review / PT 시 정직한 메시지

**좋은 메시지** (데이터로 backing 됨):
- "검증된 알고리즘 문제의 audit-able pipeline"
- "단일 LLM 대비 sample-level pass +9pp (87.7% vs 78.7%)"
- "4-tier sandbox 격리로 LLM 코드 host 격리"
- "모든 LLM call replay 가능 (cost 0 reproduction)"
- "Catalog 에 promote 된 문제는 사람 review 가능 상태"

**피해야 할 메시지** (현 데이터로 backing 안 됨):
- "고품질 문제 자체 생산" → run-level baseline 보다 낮음
- "e2e 80% success" → 실측 20%
- "Multi-mechanism 으로 deterministic" → variance 여전히 큼

### 7.4 6개월 후의 IPE 가 어떤 모습이면 좋을까

1. **catalog 에 100+ 검증된 문제 누적**. 각각 사람 review 1회 통과.
2. **노드 7개 유지** (M3 rollback 후 빈 자리는 skill library).
3. **safety 10 이하** (oscillation breaker 통합).
4. **CHANGES.md 5,000 줄 이하** (consolidation).
5. **outputs/ retention policy 자동화** — 7일 / catalog / anchor 외 archive.
6. **PT 1장으로 product positioning** — verification + catalog 중심.
7. **baseline N=10 + IPE N=10 정기 측정** — statistical power 확보.

---

## 8. 부록 — 본 분석에 사용한 데이터 출처

- `docs/baseline/v0.3.0-rc1-N3.md` (2026-05-21) — N=3 최종 측정
- `docs/baseline/v0.3.0-rc1.md` (2026-05-20) — N=1 첫 측정
- `docs/PRINCIPLES.md` (2026-05-20) — 5 운영 룰 SSOT
- `docs/rfc/v0.3.0_multi-mechanism.md` (2026-05-19) — M1~M4 design RFC
- `CHANGES.md` Round 11~23, M1~M4 sections
- `ipe/state.py` (`ProblemState` 30+ field)
- `ipe/graph.py:233~310` (build_graph 토폴로지)
- `ipe/nodes/_executor_phases.py` (576 LOC, Phase B/C 본체)
- `git log main..HEAD --all` + `git for-each-ref` (브랜치 25개)
- `du outputs workdir archive` (2.6GB / 2.2MB / 24KB)
- `aa.md` (PT 준비 신호)

---

## 9. 결론 — 한 문장으로

> **IPE 는 generation 엔진이 아니라 verification + catalog + observability
> platform 으로 재정의해야 데이터-narrative 일치를 회복할 수 있고, 다음 PR 의
> 정답은 더하기가 아니라 M3 rollback + cruft 청소 + DoD 재정의이다.**
