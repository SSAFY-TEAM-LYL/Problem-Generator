# RFC — Phase 3: Blueprint-First 생성 순서 (formal-freeze 우선, narrative-last)

| | |
|---|---|
| **Status** | Draft (2026-06-04) |
| **대상** | 메인 RFC `phase3_agentic-graph-rearchitecture.md` §5 토폴로지의 **생성 순서** — N2 Narrative ↔ N3 Formalizer |
| **관계** | 메인 RFC §5/§6 를 개정 제안하는 **보완 RFC**. 검증 계층(§7)·state(§8)·compat(§10)은 그대로 사수 |
| **동기 한 줄** | stochastic narrative-first 가 낳는 **비싼 core oscillation** 을 생성 순서로 제거 |

> 초안이다. §8 트레이드오프·§9 open questions 는 합의 전 가변.

---

## 1. 문제 — narrative-first 의 구조적 불안정

메인 RFC §5 의 front 순서는 **Strategist(N1) → Narrative(N2) → Formalizer(N3)** 다. 즉 *현실 시나리오를 먼저 쓰고, 그것을 형식 스펙으로 번역* 한다. 이 순서는 §1 의 "은닉" 동기(시나리오에서 알고리즘을 숨김)에 충실하지만, LLM 의 stochastic 성질과 만나면 두 가지 불안정을 남긴다:

1. **narrative ↔ spec drift.** 풍부한 서사를 형식화할 때 번역이 손실·모호해지면 *무엇이 "정답 문제"인지* 자체가 흔들린다. golden 을 다시 짜고 재검증하는 **비싼 core 진동** 이 발생한다.
2. **상관오해의 토양** (메인 §7.1). golden·brute 가 둘 다 *같은 prose* 에서 출발하면 같은 오독을 공유할 표면이 넓다.

v1 에 이 흔적이 박제돼 있다 — **#104 (Option B)**: architect 가 `expected_output` 을 LLM 으로 계산 → coder 출력과 충돌(sample_mismatch) → executor 가 *"invariant 통과 + mismatch → architect 가 틀림 → architect 로 back-route"* 로 우회한다 (`ipe/v1/nodes/executor.py` 주석에 남음). 이것이 정확히 *형식 스펙이 흔들려서 생긴 진동* 이다.

> 주: v2 §5 는 expected output 을 N9 Suite Assembler 의 **golden 실행** 으로 산출해 이 문제의 일부를 이미 고친다. 본 RFC 는 거기서 더 나아가 **형식 스키마 자체를 narrative 보다 먼저 freeze** 한다.

---

## 2. 제안 — 생성 순서 역전 (formal blueprint freeze → narrate last)

먼저 **형식 청사진(formal blueprint)** 을 만들어 **freeze** 하고, 그것을 단일 anchor 로 코드·테스트·지문을 *그 위에서* 생성한다. 지문은 마지막 렌더링 단계로 강등한다.

```
START
  ▼
Strategist (N1)              숨은 algo 코어 + composition + domain  → seed
  ▼
Formalizer / Blueprint (N2*) ★ formal I/O schema FREEZE:
                              - 문제 유형 / 환원(reduction) 코어
                              - 입력 구조 + 범위 + 생성기 계약(generator contract)
                              - 출력 제약 = invariant (= Tier A symbolic 후보)
  ▼  (frozen ProblemBlueprint — prose 없음)
  ├── Input Gen (schema 파생, 결정론)            ┐
  │   Golden ×K  +  Brute Oracle (독립)          │  (formal schema 만 읽음 — prose 아님)
  └──────────────────┬────────────────────────────┘
  ▼
Reconciler → [Verification: symbolic / diff / metamorphic] → Verification GATE
  ▼   (verified golden 실행으로 expected output 채움 = Suite)
  ▼
Narrative Author (N_late)    ★ frozen schema → 현실 시나리오 (은닉 렌더)
  ▼
Narrative Faithfulness (round-trip)  ★ 지문 재형식화 → frozen schema diff
  ▼
[QA: ambiguity / fairness / leakage / difficulty] → QA GATE → record
```

핵심 차이 (메인 §5 대비): **N2 Narrative 와 N3 Formalizer 의 순서를 뒤집고**, Formalizer 의 산출물(형식 스키마)을 *freeze* 해 모든 하류의 anchor 로 쓴다. 지문은 맨 마지막.

---

## 3. 왜 유리한가

### 3.1 진동은 사라지지 않고 *싼 곳으로 이동* 한다 (핵심)
narrative-first 의 진동은 **비싼 core**(golden 재작성 + 재검증)에서 일어난다. formal-first 면 core 가 frozen 이라 움직이지 않는다. 남는 반복은 오직 **narrative polish** — frozen 형식 의미는 그대로 둔 채 표현만 다듬는 *싸고 유계인* LLM 텍스트 반복(정답 재검증 불필요, faithfulness 만 확인). → **비싼 core-oscillation 을 싼 narrative-oscillation 으로 환전.** 이것이 oscillation 해소의 정확한 메커니즘이다.

### 3.2 상관오해(§7.1)가 구조적으로 내려간다
golden·brute 가 **prose 가 아니라 frozen formal schema** 를 읽는다. 형식 스키마는 prose 보다 모호성이 훨씬 낮으므로 "둘이 똑같이 오독" 할 표면이 좁아진다. 메인 §7.3 의 *무모호 spec 게이트* 가 사후 검사가 아니라 **생성 구조** 가 된다. 탈상관 유도(§7.3.1: golden=형식, brute=서사)도 자연 흡수 — 둘 다 형식에서 출발하고 narrative 는 후행.

### 3.3 "출력 제약" = symbolic invariant — verifier 가 schema 에서 파생
제안의 "출력 제약" 은 사실 **Tier A symbolic invariant 그 자체** 다. 이를 first-class 조기 산출물(blueprint 의 일부)로 두면 **verifier 가 형식 스키마에서 파생** 된다 — 지금처럼 algo 마다 손으로 짜 붙이는 게 아니라. 메인 RFC 가 걱정한 *per-algo 손작업 벽* 을 schema DSL 로 공략할 길이 열린다. (장기: invariant DSL → symbolic verifier 자동 생성.)

---

## 4. Artifact 변경 (메인 §8 위에서)

- **`ProblemBlueprint` 를 "형식 스키마" 로 승격** + **frozen**. 기존(숨은 시드 + composition + domain)에 추가:
  - `io_schema` — 입력 구조/타입/범위, 출력 타입/형식
  - `generator_contract` — 입력 생성기가 만족할 제약(분포·엣지·규모 family)
  - `output_invariants` — 출력이 항상 만족할 관계 (= symbolic invariant 후보)
  - `reduction_core` — 숨은 알고리즘/환원 (solver 만 모름, 내부 artifact 엔 명시)
- **`Narrative` 를 late artifact 로** — frozen blueprint 의 렌더링. `mode`(§10) 에 따라 직접/은닉.
- **`NarrativeFaithfulnessReport`** (신규) — round-trip 일치 결과.

---

## 5. 토폴로지 개정 (메인 §5/§6 diff)

- **이동**: N3 Formalizer → **front (N2\*)** 로, freeze. N2 Narrative → **QA 직전 late** 로.
- **신규 코드/소형 노드**: Narrative Faithfulness (round-trip).
- **불변**: Solution synth / Verification 서브그래프 / Test-suite / QA 의 4 병렬 영역, deterministic aggregator fan-in, 검증 GATE — 그대로.
- **은닉(§4①)이 어디로 가나 — 사라지지 않는다.** "알고리즘이 입력이다" 문제(메인 §1.1)는 여전히 해결된다: solver 는 frozen core 를 모르고 *은닉 narrative* 만 본다. 단 은닉이 *생성 순서* 가 아니라 **narrative 렌더링 선택**(frozen core 위의 obfuscation)으로 이동한다. 모델링(demodeling) 역량 요구는 보존.

---

## 6. 새 검증면 — narrative faithfulness

formal-first 는 "golden/brute 상관오독" 을 줄이는 대신 **"narrative 가 frozen schema 를 충실히 기술하나"** 를 새 검증면으로 만든다 (위험의 *이동* 이지 제거 아님 — 정직히 명시). 방어: **round-trip** — 생성된 narrative 를 독립적으로 재형식화(re-formalize)해 frozen schema 와 diff. 불일치 = 지문이 *다른 문제* 를 말함 → narrative 재생성(싼 반복, §3.1). 은닉 모드에선 "정보 *은닉* 은 OK, 정보 *왜곡* 은 reject" 의 구분이 필요 → §9 Q2.

---

## 7. expected output 부트스트랩 (명시)

입력은 schema 에서 결정론적 생성 가능하나, **expected output 은 golden 실행이 있어야** 안다(순환). 따라서:
- *맨 처음* freeze 되는 것은 **입력 생성기 계약 + 출력 invariant** (concrete (in, out) 쌍이 아님).
- concrete output 은 **verified golden 실행** 으로 채운다 (메인 N9 Suite Assembler 와 동일 — 이미 올바른 방향).

→ "테스트케이스 먼저" 는 정확히는 **"입력 스키마 + invariant 먼저, 정답 출력은 golden 후"**.

---

## 8. 트레이드오프 (정직)

| | narrative-first (메인 §5 현행) | blueprint-first (본 제안) |
|---|---|---|
| 진동 위치 | **비싼 core** (respec golden + 재검증) | **싼 narrative** polish |
| 상관오해 토양 | prose 공유 → 넓음 | formal 공유 → 좁음 |
| 서사 자연스러움 | 높음 (시나리오 우선 "발견") | **위험** (역설계 dress-up — 작위적일 수 있음) |
| verifier | algo 별 손작업 | schema 파생 가능 |
| 신규 비용 | — | faithfulness round-trip 노드 |

핵심 리스크 = **서사 자연스러움 저하** (frozen core 에 시나리오를 끼워맞춤 → 작위적). 완화: core 가 frozen 이라 narrative 를 *마음껏 싸게* 반복 가능 → 자연스러움은 narrative 반복으로 끌어올리되 correctness 는 불변 유지. **hiring-grade(정확성·무모호 최우선)** 에는 이 트레이드가 강하게 유리하다.

---

## 9. Open questions

- **Q1** Strategist 와 Formalizer 를 한 노드로 합칠까(둘 다 frozen blueprint 생산) vs 분리 유지?
- **Q2** faithfulness round-trip 의 *은닉 허용 vs 왜곡 거부* 경계를 어떻게 형식화? (정보-보존 검사 — 은닉은 정보 은폐, 왜곡은 정보 변조)
- **Q3** `io_schema`/`output_invariants` 를 어느 수준의 DSL 로? (자유 텍스트 → 구조화 → 실행가능 invariant 의 스펙트럼; verifier 자동생성과 직결)
- **Q4** 측정: blueprint-first 가 실제로 oscillation(fix-loop 반복수)·상관오해를 낮추는가 → narrative-first 대비 A/B (반복수 · `tier_b_recall` · faithfulness fail 율).

---

## 10. 메인 RFC 영향 / 채택 경로

- 채택 시 메인 §5(토폴로지)·§6(노드 카탈로그)의 **N2↔N3 재배치 + Narrative late + Faithfulness 노드** 추가로 개정.
- §7(tier)·§8(state)·§10(compat) **사수** — 본 제안은 *순서* 변경이지 검증/계약 변경이 아니다.
- 마일스톤 정합: M1(검증 메커니즘)은 순서와 독립이라 **무영향**. 본 재배치는 M2(병렬 solution) 착수 *전* front 를 먼저 합치는 것이 자연스럽다.
