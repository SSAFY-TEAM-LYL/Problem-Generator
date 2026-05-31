# RFC — Phase 3: Agentic Graph 재공사 (v2 pipeline)

| | |
|---|---|
| **Status** | Draft (2026-05-29) |
| **대상** | `ipe/v1/graph.py` 의 4-node linear pipeline → v2 agentic graph |
| **목표 산출물** | toy 문제 → 기업 코딩테스트 출제(hiring-grade) 수준 문제 |
| **관련 정책** | PRINCIPLES.md 룰 1~5 — 특히 **룰 4(node budget ≤8)** 갱신을 본 RFC 가 제안 |
| **선행 anchor** | v1.0 Phase 2c RCA3 = 52/57 (91.2%), samples_engaged 99.1%, 418 tests |

> 이 문서는 초안이다. §11 open questions 와 §12 마일스톤 순서는 합의 전 가변.

---

## 1. 동기 (Motivation)

v1.0 은 성공했다 — v0 27% → 91.2%, 독립 검증이라는 해자, 418 tests. 그러나 **산출물 자체가 toy 수준**이다. 코드에서 확인한 근본 원인:

1. **알고리즘이 입력이다** (`target_algorithm`). 푸는 사람이 카테고리만 봐도 무엇을 쓸지 안다. 기업 코테의 핵심 역량인 "어떤 알고리즘인지 알아내기(모델링)" 가 통째로 빠져 있다.
2. **얇은 서사** — `description` 한 필드. 시나리오를 형식 구조로 번역하는 단계가 없다.
3. **단일 기법** — 한 문제 = 한 알고리즘. 실전 상급의 기법 합성(파라메트릭 서치 + 그리디 검증 등)이 불가능.
4. **작은 인스턴스** — 난이도 입력이 없어 architect 가 N 범위를 적당히 작게 잡는다.

**B2B 비전**: 기업 코딩테스트 출제(hiring-grade, 다양한 B2B 테넌트)를 중심으로, 동일 생성 엔진 위에서 B2C 모의고사가 파생된다. toy 문제로는 둘 다 불가능하다.

**결론**: 파이프라인 토폴로지의 재설계가 필요하다. 단 v0→v1 전환에서 얻은 교훈(typed artifact + 결정론적 검증 + 측정 게이트)은 그대로 사수한다.

---

## 2. 목표 / 비목표

### Goals
- 알고리즘 **은닉** · 기법 **합성** · 구조 **풍부**한 문제를 생성한다.
- 검증 anchor 를 성숙시킨다: `symbolic` → `+ differential + metamorphic` — 복잡도가 올라도 hiring-grade 신뢰를 유지한다.
- 에이전틱 노드를 **세분화**하고, 독립적인 구간을 **병렬화**한다.
- 기존 19-algo 능력에 대해 **91.2% anchor 무회귀**.

### Non-goals (이번 RFC 범위 밖)
- greenfield 재작성 (foundation 은 사수).
- 검증 anchor 약화 — naive single-brute-trust 는 명시적 **금지**.
- B2C *전달/UI*·세트·시험 조립 — 후속 마일스톤. (단 **canonical 생성 모드** 자체는 본 RFC 범위 = 토픽 드릴, §10.3)
- 신규 알고리즘 family 대량 추가 — 본 RFC 는 "깊이" 이지 "넓이" 가 아님.

---

## 3. 사수 vs 재공사 — 경계 확정

| 사수 (다시 설계해도 동일하게 만들 것) | 재공사 (토폴로지·노드) |
|---|---|
| Pydantic typed artifact 노드 계약 | architect 1개 → **모델링 단계 분리** (Strategist / Narrative / Formalizer) |
| **결정론적 검증 anchor** (= 사업 해자) | 검증 단일 노드 → **검증 서브그래프** (symbolic + differential + metamorphic) |
| StructuredFeedback 라우팅 (`failure_mode` + `target_node`) | **Generator 노드 부활** (검증된 golden → 풀 채점 테스트셋) |
| 측정 하네스 + **91.2% 회귀 게이트** | **QA/Critic 병렬 스테이지** (모호성·공정성·유출·난이도) |
| 19 symbolic verifier (→ "정석 코어" 체크로 흡수) | 다중 기법 **합성** 메커니즘 |

핵심: **계약(typed artifact)과 해자(검증)는 유지, 그 위 토폴로지를 새로 짠다.** linear → 모델링 + 병렬 solution + 검증 서브그래프 + 병렬 QA 가 들어간 richer DAG.

---

## 4. 복잡도 frontier — 3축과 그것이 요구하는 노드

| 축 | 무엇 | 요구하는 신규 구조 |
|---|---|---|
| **① 은닉/모델링** | 지문은 현실 시나리오, 알고리즘은 숨김 | Strategist(숨은 시드) + Narrative(시나리오) + Formalizer(형식화) 분리 |
| **② 기법 합성** | 2~3 알고리즘 조합 | Strategist 의 composition pattern + 검증의 metamorphic/differential 의존 |
| **③ 구조 풍부** | 다중 엔티티·쿼리/갱신·큰 N·적대 토폴로지 | 병렬 Test-suite Generator(input family 별). 인스턴스 규모는 Formalizer 가 ad hoc 선택 (난이도 제어는 별도 RFC, R4) |

세 축 모두 **검증 천장**에 막혀 있다 — 합성·은닉되면 정석 symbolic 이 안 맞는다. 그래서 §7(검증 성숙)이 전체의 전제다.

---

## 5. 제안 토폴로지 (v2 graph)

```
START
  │
  ▼
Strategist (N1)              숨은 알고리즘 시드 + composition + 난이도 + domain
  │                          → ProblemBlueprint
  ▼
Narrative Author (N2)        blueprint → 현실 시나리오 (알고리즘 은닉)
  │
  ▼
Formalizer (N3)              시나리오 → ProblemSpec (constraints/IO/reduction, typed)
  │
  ├──────── PARALLEL: Solution Synthesis ────────┐   (fan-out)
  │   Golden ×K (N4a…)        Brute Oracle (N4b)  │
  └───────────────────┬───────────────────────────┘
  ▼
Reconciler (N5)              K golden + brute 상호 일치 확인 + canonical 채택 (fan-in, 코드)
  │
  ├──────── PARALLEL: Verification ──────────────┐   (fan-out)
  │  Symbolic(N6a)  Differential(N6b)  Metamorphic(N6c)
  └───────────────────┬───────────────────────────┘
  ▼
Verification Aggregator (N7) 적용가능 체크 전부 통과해야 verified (fan-in, 코드, GATE)
  │
  ├──────── PARALLEL: Test-suite Gen ────────────┐   (fan-out)
  │  edge(N8a) large(N8b) adversarial(N8c) random(N8d)
  └───────────────────┬───────────────────────────┘
  ▼
Suite Assembler (N9)         golden 실행 → expected output 생성 + 패키징 (fan-in, 코드)
  │
  ├──────── PARALLEL: QA / Critic ───────────────┐   (fan-out)
  │  Ambiguity(N10a) Fairness(N10b) Leakage(N10c) Difficulty(N10d)
  └───────────────────┬───────────────────────────┘
  ▼
QA Aggregator (N11)          하나라도 fail → 해당 스테이지로 back-route (fan-in, 코드)
  │
  ▼
record → router → { 임의 스테이지 재진입 | end_success | end_* }
```

**4개 병렬 영역**: Solution Synthesis / Verification / Test-suite Gen / QA. 각 영역은 fan-out → deterministic aggregator fan-in 구조 (LangGraph: parallel 브랜치가 reducer 채널에 write → join 노드가 집계 — §8).

---

## 6. 노드 카탈로그 (granular)

| # | 노드 | 책임 | 구현 | 모델 tier | 병렬 |
|---|---|---|---|---|---|
| N1 | Strategist | 숨은 algo 시드 + composition + domain (난이도는 별도 RFC, R4) | LLM | Sonnet | — |
| N2 | Narrative Author | 시나리오 작성 (은닉) | LLM | Sonnet | — |
| N3 | Formalizer | 시나리오 → ProblemSpec | LLM | **Opus** (정확성 임계) | — |
| N4a | Golden ×K | 정해 K개 (독립성 위해 모델 혼합) | LLM | Opus + Sonnet | ✅ |
| N4b | Brute Oracle | 명백히 단순한 brute | LLM | Sonnet/Haiku | ✅ |
| N5 | Reconciler | golden/brute 상호 일치 + canonical | **코드** | — | join |
| N6a | Symbolic Verifier | 정석 코어 invariant (기존 19) | **코드** | — | ✅ |
| N6b | Differential Tester | golden ↔ brute stress 차분 | **코드** | — | ✅ |
| N6c | Metamorphic Checker | 불변 관계 검사 | **코드** | — | ✅ |
| N7 | Verification Aggregator | verified 판정 GATE | **코드** | — | join |
| N8a-d | Generators | input family별 생성 | 코드(+LLM script) | Sonnet | ✅ |
| N9 | Suite Assembler | golden 실행→expected, 패키징 | **코드** | — | join |
| N10a-d | QA Reviewers | 모호성/공정성/유출/난이도 | LLM | **Haiku** | ✅ |
| N11 | QA Aggregator | fail→back-route | **코드** | — | join |

**비용 관찰**: 노드는 4→~15 로 늘지만, **신규 노드 다수가 결정론적 코드(N5/N6/N7/N9/N11, 비용 0)이거나 저가 모델(QA=Haiku)**. 비용은 N3(Formalizer) + N4(Golden×K Opus)에 집중. → **노드 수 ↑ ≠ 비용 ↑** (병렬화는 latency 만 줄이고 호출 수는 동일).

---

## 7. 검증 성숙 — make-or-break (R1 결정)

> 상세 서술: `docs/research/2026-05-29_verification-trust-tiers.md` (제3자용 쉬운 설명).

### 7.1 진짜 위협은 "상관된 오해"

differential(golden↔brute)은 **알고리즘 구현 정확성**을 이미 hiring-grade 로 잡는다 — ICPC/IOI/Codeforces 출제자가 brute stress-test 로 검증하는 실무. 약점은 거기가 아니다.

진짜 위협은 **상관된 오해(correlated spec-misinterpretation)**:

| 오류 유형 | differential 이 잡나 |
|---|---|
| **독립 오류** (golden 만 버그) | ✅ 불일치로 잡힘 |
| **상관 오류** (golden·brute 가 지문을 *똑같이* 오독) | ❌ 둘이 일치 → 거짓 확신 |

symbolic 이 특별한 이유: verifier 가 지문이 아니라 **알고리즘의 수학적 정의**에서 답을 유도 → "지문 오독" 과 독립. 즉 R1 은 "검증 강도" 가 아니라 **"지문 오독을 어떻게 탈상관하느냐"** 문제.

### 7.2 해법 — 카탈로그를 막지 않고, 문제별 신뢰 tier 로 게이트

```
Tier A (최고): 정석 코어 존재 → symbolic 적용. 완전 신뢰. (기존 19 + 은닉돼도 코어가 symbolic-checkable)
Tier B (높음): symbolic 불가, 그러나 ①신뢰가능 brute differential ②problem-class metamorphic
              ③탈상관 유도 ④무모호 spec 게이트 → 정확성 hiring-grade
Tier C (불충분): brute 신뢰 불가 / metamorphic 뿐 → B2B reject (B2C 강등 or 폐기)
```

**상한을 "symbolic-only" 로 낮추지 않는다. 문제별 도달 tier 로 거른다.** B2B 는 **Tier A/B 만 출하, Tier B 미달은 reject** (= 본 RFC 의 야심 상한 결정). 현실 코테 문제 대부분 Tier B 도달 가능(은닉 다익스트라도 brute=모든경로; 파라메트릭서치+그리디도 brute=답공간 선형스캔). brute 불가 문제는 *애초에 채용 자동출제 부적합* → reject 가 올바른 동작.

### 7.3 탈상관·벽회피 — 싸게 강화하는 두 수

1. **탈상관 유도** — golden 은 *형식 spec* 에서, brute 는 *서사 시나리오* 에서 생성. 다른 표현에서 나와 일치하면 상관오류 확률 급감 (비용 0, 입력 분리만).
2. **problem-class metamorphic** — 불변관계를 *알고리즘별*이 아니라 *문제 클래스별*(최적화/카운팅/결정/구성)로 정의. "답은 feasible", "구성한 임의 해 ≤/≥ 최적", "제약 제거 시 최적 악화 불가", "입력 스케일/순열→출력 예측가능" 등 범용. → metamorphic 이 **per-algo 손작업 벽을 재발시키지 않음**.

### 7.4 brute 독립성 4조건 (Tier B 의 ① 전제)
1. **모델 독립** — golden·brute 를 서로 다른 모델 family 로.
2. **구조 독립** — brute 는 exhaustive/naive.
3. **human-auditable 단순성** — 리뷰 가능할 만큼 단순 (복잡하면 reject).
4. **small-N exhaustive** — 작은 N 전수 검증.

### 7.5 이건 베팅이 아니라 측정 가능한 주장 (M1 의 진짜 의미)
기존 19 알고리즘은 **Tier A(symbolic)와 Tier B(differential+metamorphic)를 둘 다** 돌릴 수 있다. M1 에서:

> 19개에 대해 **Tier B 가 Tier A 와 일치하는가**를 실측 → Tier B 가 Tier A 가 잡는 걸 다 잡으면, symbolic 부재 구간에 **Tier B 를 신뢰할 권리를 측정으로 획득**.

M1 은 "differential 추가" 가 아니라 **"Tier B ≈ Tier A 임을 91.2% anchor 위에서 증명"** 하는 단계. 통과 못 하면 상한을 symbolic-only 로 낮춘다 (rollback trigger). → R1 을 베팅에서 측정된 사실로 전환.

---

## 8. State 모델 변경 (병렬 fan-in)

현재 `V1State` 는 단일 immutable Pydantic 모델을 `model_copy` 로 갱신. **병렬 노드가 동시에 전체 state 를 copy 하면 충돌**한다. 필요한 변경:

- 병렬 결과 누적용 **reducer 채널** (`Annotated[list[X], operator.add]` 스타일) — 각 병렬 노드는 자기 결과만 append, aggregator 가 fan-in 에서 읽음.
- 신규 typed artifact: `ProblemBlueprint`, `GoldenCandidate`(list), `BruteOracle`, `VerificationReport`(체크별 결과), `TestSuite`, `QAReport`(리뷰어별).
- 기존 단일 경로 필드(spec/design/attempt/verification)는 유지 — compat mode(§10)가 사용.

---

## 9. 비용 & 복잡도 규율 — 룰 4 정면 돌파

PRINCIPLES.md **룰 4: 노드 ≤8, safety ≤12.** 본 RFC 는 ~15 노드를 제안하므로 **룰 4 갱신 PR** 을 겸한다 (룰 4 자체가 "우회는 정책 업데이트 PR" 을 명시).

### v0 의 실패를 반복하지 않는 근거
v0 가 죽은 복잡도는 **누적된 ad-hoc safety 패치 10개**(trace 불가)였다. v2 의 복잡도는 **종류가 다르다**:
- **의도된 typed 구조** — 모든 노드 I/O 가 typed artifact + structured log. trace 가능.
- **ad-hoc safety 의 first-class 흡수** — v0 의 safety 들이 정식 스테이지로 승격되어 *사라진다*: reviewer→QA 스테이지, brute-oracle→검증 노드, oscillation→router. **safety count 는 오히려 ↓**.
- **병렬 = deterministic aggregator fan-in** — 분기는 반드시 코드 join 으로 수렴 (비결정 누적 없음).

### 룰 4 갱신 제안 (flat count → 구조적 규율)
> **신 룰 4**: 그래프는 **≤6 스테이지**. 각 스테이지 내 노드는 공유 typed I/O 계약을 가진다. 모든 노드는 typed artifact + structured log 를 emit 한다. 병렬 노드는 반드시 deterministic aggregator 로 fan-in 한다. (flat node count cap 폐지 — 대신 스테이지·계약·관측성으로 통제.)

### 비용 규율 (사용자의 토큰 우려 직결)
- 모델 tiering 강제 (§6): 코드/Haiku 우선, Opus 는 Formalizer·Golden 에만.
- 검증·집계는 전부 코드 = 비용 0.
- run 당 cost 를 마일스톤마다 실측해 anchor 화 (룰 3 baseline 옆).

---

## 10. Migration — strangler-fig + 측정 게이트 (R2 / ① 결정)

v0→v1 전환 playbook 그대로: 새 아키텍처를 측정 게이트에 묶어 **anchor 를 이길 때만 전진**.

### 10.1 compat flag — 한 그래프, mode typed 필드
v2 는 `mode: canonical | full` 를 blueprint 의 typed 필드로 가진다. **그래프는 하나**, 노드가 mode 로 내부 분기:
- **`canonical`**: Strategist "숨김=False/합성=없음/target_algorithm=입력" → Narrative 직접 서술 → 합성 스킵 → 정석 단일 문제 (v1 이 만들던 것).
- **`full`**: 은닉·합성·tiered 검증 전체.

→ mode 가 artifact 에 박혀 **추적 가능**(룰 4 spirit). 두 그래프 유지 부담 없음. 분기는 "플래그 읽고 prompt/검증 경로 택" 수준으로 얕게 유지.

### 10.2 anchor 2개 분업

| anchor | 모드 | metric | 역할 |
|---|---|---|---|
| **compat** | canonical, 19-algo × N≥3 | Tier A(symbolic) 통과율 vs **91.2%** | **공유 배관 회귀 가드** (사과 대 사과) |
| **full (①)** | full | **검증 통과율 = Tier B↑ 도달률 = 출하 가능률** | **신규 야심 측정**, 0부터 구축 |

compat 이 91.2 밑 → 버그는 *공유 배관*(Formalizer/solution/검증)이지 은닉 스테이지 아님 → 깨끗한 진단. full 전용 버그는 full anchor 가 감시 (분업).

### 10.3 canonical = 영구 제품 모드 (결정: 가)
canonical 은 측정 비계로 끝나지 않고 **B2C 토픽 드릴 / 입문 연습 생성 모드**로 정식 편입. → 비계가 자산이 되고, 상시 실행되어 bit-rot 없음, strangler-fig 내내 깨끗한 anchor 제공. (B2C *전달/UI*·세트조립은 여전히 후속 — §2.)

### 10.4 게이트 규율
- 마일스톤마다 compat anchor **무회귀** 확인 (룰 1 N≥3, 룰 2 cross-algorithm).
- 룰 3 단일 LLM baseline 유지, 룰 5 RCA 에 rollback trigger 명시.
- 검증 path 는 절대 끊지 않음 — 해자이자 측정 기준.

---

## 11. 리스크 & open questions

| # | 리스크 / 질문 | 비고 |
|---|---|---|
| R1 | ~~차분+metamorphic 이 hiring-grade 신뢰에 충분한가~~ **→ 결정됨 (§7)** | tier 게이트(A/B/C) + B2B 는 Tier B 이상만 출하 + M1 에서 Tier B≈Tier A 실측. 잔여 위협은 "상관된 오해" → 탈상관 유도 + 무모호 spec 게이트로 방어 |
| R2 | ~~compat mode 가 v2 복잡도와 양립하는가~~ **→ 결정됨 (§10)** | compat flag(mode typed 필드, 한 그래프) + anchor 2개 분업(compat=배관/full=야심) + canonical 영구 제품 모드 |
| R3 | 병렬 state reducer 설계 복잡도 | **M0 스파이크로 선검증** (확정) |
| R4 | 난이도 calibration | **별도 RFC 로 완전 분리** (결정 가) — 본 RFC 는 난이도-agnostic, M3 도 난이도 입력 없음. 난이도는 후속에서 *감싸는 레이어*로 |
| R5 | 비용/latency 실측치 미지 | **마일스톤마다 run당 토큰/달러 실측 + anchor 화** (확정) |
| Q1 | 마일스톤 순서 | **M1(검증 성숙) 먼저** (확정) — Tier B≈Tier A 를 값싸게 먼저 실증, 상한을 데이터로 확정 |
| Q2 | 유출검사 reference corpus | **M5 진입 시 재논의** — 외부 문제 DB 확보가 별도 과제, 지금 막을 필요 없음 |

---

## 12. 마일스톤 (multi-PR)

| M | 내용 | 게이트 | 위험 |
|---|---|---|---|
| **M0** | RFC 확정 + state reducer 스파이크 | — | 낮음 |
| **M1** | **검증 성숙 + Tier B≈Tier A 실증** — 기존 19-algo 에 differential+metamorphic 코드 추가, Tier B 가 Tier A(symbolic)와 일치함을 측정 | 91.2% 무회귀 + Tier B 일치율 | **낮음 (코드)** |
| **M2** | 병렬 solution synthesis (golden×K + brute + reconciler) | 무회귀 + 비용 실측 | 중 |
| **M3** | 모델링 layer (Strategist + Narrative + Formalizer) — **알고리즘 은닉** | 신규 anchor 구축 | 중상 |
| **M4** | Test-suite generator (풀 채점셋) | 신규 anchor | 중 |
| **M5** | QA/Critic 병렬 스테이지 (유출/공정성/모호성/난이도) | 신규 anchor | 중 |
| **M6** | 기법 합성 (multi-technique) | 신규 anchor | 높음 |

**순서 근거**: **M1(검증 성숙)을 먼저** — 코드라 가장 안전하고, 해자를 강화하며, 이후 모든 복잡도의 전제(복잡한 산출물을 신뢰할 수단)다. 그다음 병렬 토대(M2) → 가시적 non-toy 성과(M3). 단 Q1: M3 를 앞당겨 체감 성과를 먼저 낼 수도 있음 — 합의 필요.

---

## 부록 A — 현재 v1 토폴로지 (대조용)

```
START → architect → designer → coder → executor → record → router
                                                              ├─ architect
                                                              ├─ designer
                                                              ├─ coder
                                                              └─ end_{success,budget,oscillation,schema_violation} → END
```
출처: `ipe/v1/graph.py` (2026-05-29 기준).
