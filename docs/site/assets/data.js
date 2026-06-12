/* IPE site — shared data for all pages
 * SPEC / ARCHITECTURE / CHANGES / RFC 의 데이터를 inline JS 상수로 노출.
 * 모든 페이지에서 import 없이 window 전역으로 접근.
 *
 * 모든 수치는 측정/문서 근거가 있는 값만 적는다 (narrative honesty).
 * 갱신: 2026-06-12 — v1.0 출시(anchor freeze) + Phase 3(v2) M0~M6 전부 구현 완료 반영.
 */

window.IPE_DATA = {
  meta: {
    version: "v1.0 · Phase 3 (v2) 진행 중",
    repo: "https://github.com/LsMin124/IPE",
    mainCommit: "5035f29",          // main HEAD — API 배포 Slice 2 (Dockerfile.api + 배포 가이드 + 컨테이너 smoke, #145)
    devBranch: "— (v2 M0~M6 main 병합 완료)",
    devCommit: "5035f29",           // 활성 dev 트랙 없음 — v2 + API delivery layer main 통합
    updated: "2026-06-13",

    // v1.0 측정 anchor (Phase 2c RCA3 final = CHANGES §67, freeze)
    gatePass: "52/57",
    gatePassPct: 91.2,
    sampleLevel: 97.7,
    samplesEngaged: 99.1,
    baselineV0Pct: 27,              // v0 8/30
    improvementPp: 64,
    algoCatalog: 19,
    meanIteration: 1.07,

    // 코드 베이스 (측정값)
    tests: 705,                     // v1 557 + v2 148 collected (이번 주기 collect-only 실측; API 서버 #144~145 로 v2 +11)
    testsSkipped: 3,
    coverage: 87,                   // ipe/v1 scope, pytest-cov 실측
    coverageScope: "ipe/v1",
    nodes: 4,                       // v1 실행 파이프라인 노드 (architect→designer→coder→executor)
    v2Nodes: 15,                    // v2 제안 토폴로지 (RFC §5)
    deps: 14,                       // core 9 (+fastapi +uvicorn) + dev 5

    // honest positioning — "고품질 자체 생산" 이 아니라 검증·계약·측정·관측
    tagline: "알고리즘 문제를, 코드가 독립적으로 검증할 수 있는 형태로 생성한다.",
    summary:
      "v1.0 출시 완료 (anchor freeze). v0 27% → 91.2% (52/57), 19 algorithm catalog, " +
      "samples_engaged 99.1%, mean iteration 1.07. 해자는 '고품질 LLM 생산'이 아니라 " +
      "정답을 코드가 알고리즘의 수학적 정의에서 유도하는 독립 검증 + typed artifact 라우팅 + 측정 게이트다. " +
      "Phase 3 = v2 agentic graph 재공사 — RFC 마일스톤 M0~M6 전부 구현 완료. 시드→blueprint→narrative 은닉→faithfulness→spec→synthesis→verification→풀 채점셋→QA 4관점 게이트→기법 합성 전 경로 배선, QA fail 시 자동 back-route(revise→재리뷰)까지 실 LLM 으로 실증. 이후 spec 저작 가드(#141)·composition 다양성 규율(#142)·전 노드 템플릿 변수 무결성 게이트(#143)로 견고화. 이어 HTTP delivery layer 착수 — FastAPI API 서버(generate/jobs/healthz, B2C 계약 v1.0, #144) + Dockerfile.api·배포 가이드·컨테이너 실 LLM smoke(#145). v1(canonical)은 CANONICAL.md 로 동결, ipe/v2 가 fresh 파이프라인. 다음은 정리·전달 국면(API 확장·leakage corpus·docs).",
  },

  // ── 해자 (왜 이 산출물을 신뢰할 수 있는가) ─────────────────────────
  moat: [
    {
      icon: "🔬",
      title: "독립적·결정론적 검증",
      desc: "정답을 LLM 이 아니라 코드가 알고리즘의 수학적 정의에서 유도한다 — 19개 symbolic verifier. " +
        "지문 오독과 독립적이라 '그럴듯한 오답'을 결정론적으로 걸러낸다.",
    },
    {
      icon: "📐",
      title: "Typed artifact 계약 + 구조화 라우팅",
      desc: "Pydantic v2 노드 계약 (ProblemSpec / AlgorithmDesign / SolutionAttempt / VerificationResult) + " +
        "StructuredFeedback (failure_mode + target_node) → 실패가 어느 노드 책임인지 결정론적으로 라우팅.",
    },
    {
      icon: "📊",
      title: "측정 게이트 (91.2% anchor)",
      desc: "모든 변경은 N≥3 cross-algorithm 측정 게이트를 통과해야 머지된다. " +
        "over-correction 은 rollback (M3 가 첫 사례). 신뢰를 주장이 아니라 측정으로 획득한다.",
    },
    {
      icon: "🔭",
      title: "관측성 · 재현성",
      desc: "모든 LLM 호출 raw trace 보존 + SqliteSaver checkpoint → replay 0-cost 재현. " +
        "outputs/<run_id>/ 에 spec/code/verification + problem.md + samples (online judge 호환) 영속화.",
    },
  ],

  // ── v0 → v1.0 측정 여정 (Gate 통과율 + 카탈로그 성장) ──────────────
  // 출처: CHANGES §41~§67, baseline/*
  journey: [
    { phase: "v0 baseline",          algos: 0,  passPct: 27.0, label: "8/30",  note: "M1~M4 누적 mechanism (~120 cycle) 한계 — toy 수준 진단" },
    { phase: "Phase 1 (Dijkstra)",   algos: 1,  passPct: 100.0, label: "3/3",  note: "typed artifact + symbolic verifier + structured routing 도입 (MVR)" },
    { phase: "Phase 2a",             algos: 5,  passPct: 93.3, label: "14/15", note: "samples_engaged 100%, H2(verifier engagement) 강한 evidence" },
    { phase: "Phase 2b",             algos: 13, passPct: 87.2, label: "34/39", note: "cluster verifier 패턴 (1 enum = family). Knapsack outlier 첫 식별" },
    { phase: "Phase 2c",             algos: 19, passPct: 82.5, label: "47/57", note: "Graph+DS+DP family 확장. Knapsack/Kruskal outlier RCA candidate" },
    { phase: "Phase 2c · RCA3",      algos: 19, passPct: 91.2, label: "52/57", note: "P1~P3 RCA 회복 + outputs 영속화 → anchor freeze (v1.0)" },
  ],

  // ── v1.0 실행 파이프라인 (실제 동작 — 4 LLM 노드) ─────────────────
  // 출처: ipe/v1/graph.py
  graphNodes: [
    { id: "architect", label: "Architect",          model: "Opus",   desc: "ProblemSpec — storytelling + structured constraints + 3~5 sample testcases" },
    { id: "designer",  label: "Algorithm Designer", model: "Sonnet", desc: "algorithm 선택 + pseudocode + complexity + edge cases (Coder 분해)" },
    { id: "coder",     label: "Coder",              model: "Opus",   desc: "golden(정해) + brute oracle 동시 구현 + LESSON 누적" },
    { id: "executor",  label: "Executor",           model: "code",   desc: "symbolic verifier + sample/brute cross-check → StructuredFeedback 라우팅" },
  ],

  // ── Phase 3 = v2 agentic graph (RFC §5 제안 토폴로지) ─────────────
  v2Stages: [
    { stage: "Modeling",            nodes: ["Strategist", "Narrative Author", "Formalizer"],                 parallel: false, desc: "알고리즘 은닉 — 숨은 시드 → 현실 시나리오 → 형식 ProblemSpec" },
    { stage: "Solution Synthesis",  nodes: ["Golden ×K", "Brute Oracle", "Reconciler"],                      parallel: true,  desc: "독립 모델 정해 K개 + brute, 코드 reconcile (fan-in)" },
    { stage: "Verification",        nodes: ["Symbolic", "Differential", "Metamorphic", "Aggregator·GATE"],   parallel: true,  desc: "Tier A/B/C 신뢰 게이트 — 적용가능 체크 전부 통과해야 verified" },
    { stage: "Test-suite Gen",      nodes: ["edge", "large", "adversarial", "random", "Assembler"],          parallel: true,  desc: "input family 별 생성 → golden 실행 expected → 패키징" },
    { stage: "QA / Critic",         nodes: ["Ambiguity", "Fairness", "Leakage", "Difficulty", "Aggregator"], parallel: true,  desc: "모호성/공정성/유출/난이도 (Haiku) → fail 시 back-route" },
  ],

  // ── 검증 신뢰 tier (RFC §7 — make-or-break 결정) ──────────────────
  tiers: [
    { tier: "A", label: "최고 신뢰",            cls: "success", desc: "정석 코어 존재 → symbolic 적용. 완전 신뢰. (기존 19 + 은닉돼도 코어가 symbolic-checkable)" },
    { tier: "B", label: "높은 신뢰 · B2B 출하 하한", cls: "accent",  desc: "신뢰가능 brute differential + problem-class metamorphic + 탈상관 유도 + 무모호 spec 게이트 → hiring-grade" },
    { tier: "C", label: "불충분 → reject",      cls: "danger",  desc: "brute 신뢰 불가 / metamorphic 뿐 → B2B reject (B2C 강등 or 폐기). 진짜 위협은 '상관된 오해'." },
  ],

  // ── Phase 3 마일스톤 (RFC §12) ────────────────────────────────────
  milestones: [
    { id: "M0", title: "RFC 확정 + state reducer 스파이크",                          status: "done",        ref: "#107 · #108", note: "병렬 fan-in reducer 선검증 — frozen Pydantic + reducer 동작 확인 (langgraph 1.2.2). partial dict 반환 + order-independent aggregator 필수." },
    { id: "M1", title: "검증 성숙 — Tier B ≈ Tier A 실증",                           status: "done",        ref: "#109", note: "differential(golden↔brute) + metamorphic(범용 관계) + tier classifier(A/B/C 게이트) 완성. 19-algo tier sensitivity 일괄 배선으로 Tier B≈Tier A 실측 증거 확보." },
    { id: "M2", title: "병렬 solution synthesis (golden×K + brute + reconciler)",   status: "done",        ref: "#110~#113", note: "fan-out 서브그래프 + reducer 채널 + Reconciler + compat flag(canonical|full). full mode 실 LLM e2e(distinct-model golden×2 + brute) 통과." },
    { id: "M3", title: "모델링 layer — 알고리즘 은닉 (Strategist/Narrative/Formalizer)", status: "done", ref: "#116~#120", note: "ipe/v2 V2State(#116) → Strategist/Formalizer(#117) → Narrative 은닉(#118) → Faithfulness round-trip(#119) → 그래프 배선 종료(#120). 알고리즘 은닉 4노드 + 충실성 검증 완성." },
    { id: "M4", title: "Test-suite generator (풀 채점셋)",                          status: "done",        ref: "#126~#129", note: "test-suite 스키마+producer+입력생성기(graph/grid)+assembler 배선, io_contract canonical 렌더 freeze(직렬화↔골든 파서 정렬). assembled ratio 0→1.000 실측 회복." },
    { id: "M5", title: "QA/Critic 병렬 스테이지 (유출/공정성/모호성/난이도)",          status: "done",        ref: "#130~#136", note: "4 리뷰어 fan-out + aggregator 게이트, reconcile reject 진단, CLI --with-qa/--with-test-suite 노출. narrative 형식서술 금지(A)·formalizer 고아필드 금지(A2)·QA fail→revise→재리뷰 back-route(B) 실증." },
    { id: "M6", title: "기법 합성 (multi-technique)",                              status: "done",        ref: "#137~#140", note: "Tier B 검증 스위치 + 합성 실현 규율, 간선 다속성 금지 + composed 샘플 검산, 경계/퇴화 의미론 규율(#140). 재측정 N=3: 다속성 모순 소멸 + composed verification 회복." },
  ],

  // ── 최근 대표 PR (v1.0 마무리 → Phase 3 착수) ─────────────────────
  recentPrs: [
    { num: 113, title: "M2 — full mode 실 LLM e2e",                      type: "test", impact: "distinct-model golden×2 + brute 통과" },
    { num: 120, title: "M3 — 모델링 layer 그래프 배선 (step 5, M3 종료)", type: "feat", impact: "알고리즘 은닉 4노드 graph 통합 완료" },
    { num: 124, title: "v2 통합 — synthesis 그래프 배선 완성 (step2b)",     type: "feat", impact: "M2+M3 v2 그래프 통합 완성" },
    { num: 125, title: "v2-cli — --with-synthesis + full 파이프라인 실 LLM e2e", type: "feat", impact: "synthesis 경로 CLI 개방 + 종단 검증" },
    { num: 126, title: "M4 — test-suite 스키마+producer+입력생성기+assembler", type: "feat", impact: "풀 채점셋 생성 layer 배선 (step1-5)" },
    { num: 127, title: "M4 — graph/grid 입력 생성 (weighted/tree/grid)", type: "feat", impact: "input family 확장 (step3b)" },
    { num: 128, title: "M4 — suite e2e dijkstra seed + assembler 진단",   type: "feat", impact: "all-fail 진단 anchor 실측" },
    { num: 129, title: "M4 — io_contract canonical 렌더 freeze",          type: "feat", impact: "직렬화↔골든 파서 정렬, assembled ratio 0→1.000" },
    { num: 130, title: "M5 — QA/Critic 병렬 스테이지 (4 리뷰어 fan-out)",  type: "feat", impact: "모호성/공정성/유출/난이도 + aggregator 게이트" },
    { num: 132, title: "M5 — CLI --with-test-suite/--with-qa 노출",        type: "feat", impact: "M4/M5 스테이지 전 경로 CLI 개방" },
    { num: 134, title: "M5 — narrative 형식서술 금지 규율 (A)",            type: "feat", impact: "지문↔io_contract 모순 원천 차단" },
    { num: 135, title: "M5 — formalizer 고아필드 금지 + faithfulness 결손 (A2)", type: "feat", impact: "스키마 의미 정합 — 결손 데이터 왜곡 판정" },
    { num: 136, title: "M5 — QA back-route 루프 (fail→revise→재리뷰)",     type: "feat", impact: "QA findings 피드백 → desc 패치 회수 실증 (B)" },
    { num: 137, title: "M6 — 기법 합성 step1-2 (Tier B 스위치 + 실현 규율)", type: "feat", impact: "2~3 알고리즘 조합 합성 진입" },
    { num: 139, title: "M6 — step4 간선 다속성 금지 + composed 샘플 검산", type: "feat", impact: "다속성 모순 소멸 + composed verification 회복" },
    { num: 140, title: "v2 — 경계/퇴화 케이스 의미론 규율 (formalizer invariants)", type: "feat", impact: "명시 결정 + narrative 의미 서술" },
    { num: 141, title: "v2 — spec 저작 가드 (structured output 전멸 → fail_spec_authoring)", type: "feat", impact: "crash 대신 결정론적 fail 종료" },
    { num: 142, title: "v2 — composition 다양성 규율 (내장 기법 장식·최빈 패턴 고정 금지)", type: "feat", impact: "합성 다양성 ↑ — leakage 직결 변수 제어" },
    { num: 143, title: "v2 — spec_bridge 중괄호 이스케이프 + 전 노드 템플릿 변수 무결성 게이트", type: "fix", impact: "프롬프트 템플릿 변수 누락 결정론 차단" },
    { num: 144, title: "API 서버 Slice 1 — B2C 계약 v1.0 (generate/jobs/healthz)", type: "feat", impact: "FastAPI HTTP delivery layer 착수" },
    { num: 145, title: "API 배포 Slice 2 — Dockerfile.api + 배포 가이드 + 컨테이너 smoke", type: "feat", impact: "컨테이너 실 LLM smoke 검증" },
  ],

  // ── 후속 / 별도 트랙 (본 RFC 범위 밖, 추적용) ─────────────────────
  backlog: [
    { id: "R4 난이도 calibration",  priority: "별도 RFC", desc: "본 RFC 는 난이도-agnostic — 후속에서 감싸는 레이어로 분리" },
    { id: "B2C 전달/세트 조립",     priority: "후속",     desc: "canonical 토픽 드릴 모드는 v2 범위, UI·세트·시험 조립은 후속" },
    { id: "Multi-lang 솔루션",      priority: "v2.x",     desc: "C++ / Go / Rust — _write_source 분기 추가" },
    { id: "M4 stress 입력 생성기",  priority: "M4",       desc: "본격 stress 입력 생성 — M1 실측은 우선 기존 sample 입력(무료)으로" },
  ],

  // ── 핵심 원칙 (PRINCIPLES.md) ─────────────────────────────────────
  principles: [
    { icon: "📏", title: "측정 우선", desc: "N≥3 측정 + baseline anchor 없이는 머지하지 않는다. 추가 측정이 diminishing returns 면 중단하고 freeze." },
    { icon: "🧭", title: "해자 사수", desc: "재공사해도 typed artifact 계약 + 결정론적 검증 anchor 는 사수. 검증 path 는 절대 끊지 않는다." },
    { icon: "🪢", title: "복잡도 규율", desc: "그래프는 ≤6 스테이지, 모든 노드는 typed artifact + structured log emit, 병렬은 반드시 deterministic aggregator 로 fan-in." },
    { icon: "💸", title: "비용 규율",   desc: "모델 tiering 강제 (코드/Haiku 우선, Opus 는 Formalizer·Golden 에만). 검증·집계는 코드 = 비용 0. run당 비용 마일스톤마다 실측." },
  ],

  // ── FR (기능 요구사항) — v1.0 기준 ────────────────────────────────
  fr: [
    { id: "FR-1",  title: "문제 자동 생성 (Architect)",  desc: "algorithm 키워드 → storytelling + structured constraints + 3~5 sample testcases" },
    { id: "FR-2",  title: "알고리즘 설계 (Designer)",    desc: "Coder 분해 — algorithm 선택 + pseudocode + complexity + edge cases" },
    { id: "FR-3",  title: "정해+brute 작성 (Coder)",     desc: "golden(정해) 과 brute oracle 동시 구현 + LESSON 누적" },
    { id: "FR-4",  title: "독립 검증 (Executor)",        desc: "19 symbolic verifier — 알고리즘 정의에서 답 유도, 지문 오독과 독립" },
    { id: "FR-5",  title: "brute cross-check",           desc: "sample 불일치 시 brute oracle 로 architect expected_output 정확성 결정론 검증" },
    { id: "FR-6",  title: "구조화 라우팅",               desc: "StructuredFeedback (failure_mode + target_node) → 실패 책임 노드로 결정론 라우팅" },
    { id: "FR-7",  title: "4-Tier Sandbox",              desc: "Docker / nsjail / sandbox-exec / RLIMIT 자동 선택 — 생성 코드 격리 실행" },
    { id: "FR-8",  title: "Resume & Replay",             desc: "SqliteSaver checkpoint + LLM raw trace → 0-cost 재현" },
    { id: "FR-9",  title: "비용 가드",                   desc: "max_cost_usd 초과 시 halt + LLMCallTracker" },
    { id: "FR-10", title: "관측성 (LLM trace)",          desc: "raw input/output 디스크 저장 + 옵션 LangSmith/OTel" },
    { id: "FR-11", title: "산출물 영속화",               desc: "outputs/<run_id>/ — spec/design/code/verification + problem.md + samples/NN.{in,out}" },
    { id: "FR-12", title: "반복 제어 (3중)",             desc: "max_iter (안전망) + per-node budget (정밀) + cost guard" },
    { id: "FR-13", title: "Oscillation 차단",            desc: "동일 signature 반복 시 라우팅 레벨 결정론 차단 (architect↔coder 대칭)" },
    { id: "FR-14", title: "측정 하네스",                 desc: "N≥3 × multi-algo Gate 측정 runner + samples_engaged 추적 + outputs opt-in" },
  ],

  // ── NFR (비기능) — 측정값 반영 ────────────────────────────────────
  nfr: [
    { id: "NFR-1",  title: "정확성",      metric: "Gate 52/57 (91.2%), sample-level 97.7%, samples_engaged 99.1%, mean iter 1.07" },
    { id: "NFR-2",  title: "안정성",      metric: "Sandbox 격리 + checkpoint resume + race 0 (PHASE_C_WORKERS=1)" },
    { id: "NFR-3",  title: "보안",        metric: "API key .env / 코드 sandbox / network 차단 (T1)" },
    { id: "NFR-4",  title: "확장성",      metric: "algorithm = cluster verifier 패턴 (1 enum = family), 언어 추가 = 함수 분기" },
    { id: "NFR-5",  title: "유지보수성",  metric: "파일 ≤ 800 lines, mypy --strict 0, ruff 0" },
    { id: "NFR-6",  title: "테스트 품질", metric: "v1 557 + v2 148 collected, coverage 87% (ipe/v1), mypy --strict 0 · ruff 0" },
    { id: "NFR-7",  title: "비용 효율",   metric: "1 run 실측 $0.4~0.6 (백엔드 계약 §5 정정), list price 대비 ≈0.4x (Tier+cache)" },
    { id: "NFR-8",  title: "관측성",      metric: "LLM trace + replay + outputs/ 영속화 + LangSmith/OTel 옵션" },
    { id: "NFR-9",  title: "운영성",      metric: "make install / ipe CLI / resume·replay / measurement runner" },
    { id: "NFR-10", title: "재현성",      metric: "seed-deterministic 검증 + replay 100% + run-id 격리 outputs" },
  ],

  // ── Tech stack (TECH_STACK.md 미러, v1.0 실제 반영) ───────────────
  stack: {
    runtime: [
      { name: "Python", version: "3.11+", note: "Pydantic v2 typed artifacts + asyncio + mypy --strict 호환" },
      { name: "Java", version: "17 Temurin", note: "옵션 — Java 솔루션 시" },
    ],
    llm: [
      { name: "langgraph", version: "≥0.2.0 (런타임 1.2.x)", note: "노드 그래프 오케스트레이션 — v2 병렬 reducer 채널" },
      { name: "langgraph-checkpoint-sqlite", version: "≥3.0.0", note: "SqliteSaver — resume/replay" },
      { name: "langchain-anthropic", version: "≥0.2.0", note: "ChatAnthropic wrapper" },
      { name: "anthropic", version: "≥0.40.0", note: "SDK" },
    ],
    sandbox: [
      { tier: "T1",   name: "Docker",       env: "all OS (daemon)", note: "Network 차단 + readonly rootfs + bind mount + cgroup" },
      { tier: "T2",   name: "nsjail",       env: "Linux only",       note: "namespace + seccomp + cgroup" },
      { tier: "T2.5", name: "sandbox-exec", env: "macOS only",       note: "Apple Seatbelt" },
      { tier: "T3",   name: "POSIX RLIMIT", env: "all OS (fallback)", note: "RLIMIT_AS/CPU/NPROC" },
    ],
    quality: [
      { name: "pytest", version: "≥8.0.0", note: "테스트 러너 — v1 557 + v2 148 collected" },
      { name: "pytest-mock", version: "≥3.12.0", note: "LLM mock" },
      { name: "pytest-cov", version: "≥4.1.0", note: "coverage 87% (ipe/v1)" },
      { name: "ruff", version: "≥0.5.0", note: "lint (E/F/W/I/N/UP/B/C4/SIM) — 0 errors" },
      { name: "mypy", version: "≥1.10.0", note: "--strict 0 errors" },
    ],
    other: [
      { name: "pydantic", version: "≥2.0.0", note: "typed artifact 노드 계약 (v1 D안 도입)" },
      { name: "python-dotenv", version: "≥1.0.0", note: ".env 환경 변수" },
      { name: "jsonschema", version: "≥4.20.0", note: "LLM 출력 schema 검증" },
      { name: "fastapi", version: "≥0.115", note: "HTTP delivery layer — generate/jobs/healthz (B2C 계약 v1.0, #144)" },
      { name: "uvicorn", version: "≥0.30", note: "ASGI 서버 — Dockerfile.api 컨테이너 배포 (#145)" },
    ],
  },

  // ── 제외 기술 + 이유 ──────────────────────────────────────────────
  exclusions: [
    { tech: "OpenAI SDK", reason: "Anthropic 단일 provider (langchain-anthropic 으로 충분)" },
    { tech: "Flask / Django", reason: "HTTP delivery 는 FastAPI 채택 (#144~145) — 경량 ASGI + Pydantic 계약 정합. Flask/Django 는 과함" },
    { tech: "Celery / Redis", reason: "단일 사용자/run — 큐 불필요" },
    { tech: "PostgreSQL", reason: "출력 JSON/디렉토리로 충분 (DB-insertable schema)" },
    { tech: "TypedDict", reason: "v1 D안에서 Pydantic v2 typed artifact 로 전환 — 검증·계약 강화" },
    { tech: "Black + isort", reason: "ruff 통합 (single-tool 정책)" },
    { tech: "Poetry / Hatch", reason: "setuptools + requirements.txt 로 충분" },
  ],
};
