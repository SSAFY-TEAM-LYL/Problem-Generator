/* IPE site — shared data for all pages
 * SPEC / ARCHITECTURE / CHANGES / RFC 의 데이터를 inline JS 상수로 노출.
 * 모든 페이지에서 import 없이 window 전역으로 접근.
 *
 * 모든 수치는 측정/문서 근거가 있는 값만 적는다 (narrative honesty).
 * 갱신: 2026-06-22 — v2 그래프 완료 후 전달/연동 스택 반영 (API·공유 DB·P1/P2·난이도·알고리즘 정션·공개번호·계약 v3.1).
 */

window.IPE_DATA = {
  meta: {
    version: "v1.0 · v2 그래프 + 단일 IR 아키텍처 · 초급 트랙",
    repo: "https://github.com/LsMin124/IPE",
    mainCommit: "c59244a",          // main HEAD — sequence write-side N=0/sortedness 단일소스화 (#175)
    devBranch: "— (단일-IR 아키텍처 Phase 2~5a + 백본 일반화 G0~G2 + 초급 트랙: #172·#174·#175)",
    devCommit: "c59244a",           // 활성 dev 트랙 없음 — #172 단일-IR + #174 초급 트랙 + #175 sequence 모순해소 까지 통합
    updated: "2026-06-26",

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
    tests: 862,                     // v1 515 + v2 347 collected (c59244a worktree 실측; #172 단일-IR Phase 2~5a +#174 초급 +#175 로 +94)
    testsSkipped: 3,
    coverage: 87,                   // ipe/v1 scope, pytest-cov 실측
    coverageScope: "ipe/v1",
    nodes: 4,                       // v1 실행 파이프라인 노드 (architect→designer→coder→executor)
    v2Nodes: 15,                    // v2 논리 노드 (RFC §5 설계 — ipe/v2 그래프로 구현 완료, 실제 graph add_node 30: 제어/종단 포함)
    deps: 16,                       // core 11 (+fastapi +uvicorn +sqlalchemy +psycopg) + dev 5
    contract: "v3.1",              // 백엔드 전달 계약 — mode p1/p2 + difficulty + algorithm 정션 + problem_number

    // honest positioning — "고품질 자체 생산" 이 아니라 검증·계약·측정·관측
    tagline: "알고리즘 문제를, 코드가 독립적으로 검증할 수 있는 형태로 생성한다.",
    summary:
      "v1.0 출시 완료 (anchor freeze). v0 27% → 91.2% (52/57), 19 algorithm catalog, " +
      "samples_engaged 99.1%, mean iteration 1.07. 해자는 '고품질 LLM 생산'이 아니라 " +
      "정답을 코드가 알고리즘의 수학적 정의에서 유도하는 독립 검증 + typed artifact 라우팅 + 측정 게이트다. " +
      "Phase 3 = v2 agentic graph 재공사 — RFC 마일스톤 M0~M6 전부 구현 완료. 시드→blueprint→narrative 은닉→faithfulness→spec→synthesis→verification→풀 채점셋→QA 4관점 게이트→기법 합성 전 경로 배선, QA fail 시 자동 back-route(revise→재리뷰)까지 실 LLM 으로 실증. 이후 spec 저작 가드(#141)·composition 다양성 규율(#142)·전 노드 템플릿 변수 무결성 게이트(#143)로 견고화. " +
      "이어 전달/연동 국면 — 생성 엔진을 실제 서비스에 연결하는 스택을 구축했다. HTTP delivery layer (FastAPI generate/jobs/healthz, #144~145) + 배치 검증/문제 은행 적재 CLI(#146) + 출하 병목 규율(코더 파서·입력 캡 #147, QA 하류 #148, tie-break #149). 그리고 공유 PostgreSQL 문제 은행 직접 적재(#150)·결정적 파서 주입(#151)·composition/도메인 회전 팔레트로 leakage 구조적 분산(#152·#159)·synthesis 견고화(#153~154)·QA 리뷰어 Sonnet 승급(#156)·문제 은행 관리 콘솔(#155)·QA-fix remediation(#158)·canonical/hybrid ingest(#160). " +
      "별도 트랙 R4 난이도 — 판별 에이전트로 BOJ 티어 calibration 착수(#161), solved.ac 실측 20티어(Bronze~Platinum) anchor 확장(#162). 그리고 #163 에서 3세대(v0/v1/v2) → 2 파이프라인 수렴(레거시 v0 제거 + v1 prune), 이어 P1/P2 2-모드 수렴(#164~165, 계약 v2.0) — 한 모드 노브가 합성·은닉·지문·QA관점 4축을 결정한다(p1=단일·공개·QA 3종 / p2=합성·은닉·QA 4종). " +
      "최근에는 백엔드 연동을 위해 계약을 끌어올렸다 — 알고리즘 분류를 N:M 정션(problem_algorithms, core+composition role)으로 교체(#166, 계약 v3.0), UUID 와 별개의 사람용 공개 검색 번호 problem_number(BOJ식 1000~)를 추가(#167, v3.1), 공유 docs 재정리(#168). prod DB 마이그레이션(0003→0005) 적용 — 25문제 무손실 이행. " +
      "이어 출하율(ship-rate)을 진단·수선했다 — P1 출하율 N=18 진단(authoring 정합성 결함) → 입력생성·정합성 fix 로 P1 1/9→6/9(11%→67%) 실측 회복(#169), prod 6문제 추가 적재(#1025~1030 → 31문제). 그리고 모순 표면을 구조적으로 붕괴시키는 단일 ProblemIR 아키텍처를 구축했다 — 단일 IR + 순수 투영(generator_designer/spec_bridge→io_schema) + 검증 슬롯 2개로 노드 간 정합성 검사 O(N²)→O(2)(consistency-by-construction). Phase 0(출하율 수선, #169) → Phase 1 구조 IR 필드(#170~171) → Phase 2~5a IR validator + 순수투영 + 백본 일반화 G0~G2(#172) 완결. 이어 초급 문제 트랙(seed-파생 난이도 + difficulty 완화 + abstract orthogonal, #174)·sequence write-side N=0/sortedness 모순 해소(#175). 다음은 출하율 재측정·leakage corpus(Q2).",
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

  // ── Phase 3 = v2 agentic graph (RFC §5 — ipe/v2 그래프로 구현 완료) ─────────────
  v2Stages: [
    { stage: "Modeling",            nodes: ["Strategist", "Narrative Author", "Formalizer"],                 parallel: false, desc: "알고리즘 은닉 — 숨은 시드 → 현실 시나리오 → 형식 ProblemSpec (P2 모드)" },
    { stage: "Solution Synthesis",  nodes: ["Golden ×K", "Brute Oracle", "Reconciler"],                      parallel: true,  desc: "독립 모델 정해 K개 + brute, 코드 reconcile (fan-in)" },
    { stage: "Verification",        nodes: ["Symbolic", "Differential", "Metamorphic", "Aggregator·GATE"],   parallel: true,  desc: "Tier A/B/C 신뢰 게이트 — 적용가능 체크 전부 통과해야 verified" },
    { stage: "Test-suite Gen",      nodes: ["edge", "large", "adversarial", "random", "Assembler"],          parallel: true,  desc: "input family 별 생성 → golden 실행 expected → 패키징" },
    { stage: "QA / Critic",         nodes: ["Ambiguity", "Fairness", "Leakage", "Difficulty", "Aggregator"], parallel: true,  desc: "모호성/공정성/유출/난이도 (Sonnet, #156 승급) → fail 시 back-route. P1=3종(유출 제외)·P2=4종" },
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

  // ── 전달 · 연동 스택 (v2 그래프 완성 후 서비스 연결 — #144~#168) ───────────
  // 생성 엔진을 실제 백엔드/서비스에 연결하는 인프라. 모두 main 병합 + 계약 문서 동기화.
  delivery: [
    { icon: "🌐", title: "HTTP API (FastAPI)",       ref: "#144~145", desc: "generate / jobs / healthz 엔드포인트 + golden_elapsed_ms 메타. Dockerfile.api 컨테이너 배포 + 실 LLM smoke. B2C 계약 v1.0 착수." },
    { icon: "🗄️", title: "공유 PostgreSQL 문제 은행",  ref: "#150·#155", desc: "파이프라인이 검증 통과 문제를 공유 DB 에 직접 적재 (SQLAlchemy Core + psycopg). 단일 페이지 CRUD 관리 콘솔(ipe.v2.admin)." },
    { icon: "🎚️", title: "P1 / P2 2-모드 수렴",         ref: "#163~165", desc: "3세대(v0/v1/v2) → 2 파이프라인 정리. 한 모드 노브가 합성·은닉·지문·QA관점 4축 결정 — p1=단일·공개·QA 3종 / p2=합성·은닉·QA 4종. 계약 v2.0 breaking." },
    { icon: "🏅", title: "난이도 calibration (R4)",     ref: "#161~162", desc: "판별 에이전트가 패키지를 solved.ac 실측 20티어(Bronze~Platinum)로 BOJ 보정. problems.difficulty 1급 컬럼 (응시자 비노출). seam 기본 off." },
    { icon: "🔗", title: "알고리즘 N:M 분류 정션",      ref: "#166",     desc: "problems.algorithm 스칼라 → problem_algorithms(problem_id, algorithm, role[core|composition]). 백엔드 필터링이 합성 기법까지 가져가도록. 계약 v3.0." },
    { icon: "🔢", title: "공개 검색 번호 problem_number", ref: "#167",   desc: "UUID 와 별개의 사람용 공개 정수 번호 (BOJ식 1000~, advisory-lock 직렬 채번). 검색·노출용 핸들. 계약 v3.1 additive." },
    { icon: "📄", title: "백엔드 전달 계약 v3.1",        ref: "#165·#168", desc: "contract / db-access / deploy 3문서 동기화 + 변경이력. mode p1/p2 + difficulty + algorithm 정션 + problem_number 까지 반영. 공유 repo 핸드오프 준비 완료." },
  ],

  // ── 문제 은행 prod 스냅샷 (2026-06-22 마이그레이션 0003→0005 직후) ──────────
  // prod DB 무손실 이행 실측값 — 드리프트 가능, 스냅샷으로 명시.
  bank: {
    asOf: "2026-06-24",
    head: "0005",
    problems: 31,
    numberFrom: 1000,
    numberTo: 1030,
    algoCore: 31,
    algoComposition: 44,
    algoDistinct: 18,
    difficulty: "Bronze 3 / Silver 10 / Gold 18",
    note: "검증 통과 문제만 적재. #169 출하율 수선으로 P1 6문제 추가(#1025~1030, 모두 P1=단일이라 composition 0). 백엔드 연동 대기 (소비자 0). 번호는 적재 시점 채번, draft 탈락분 결번 허용.",
  },

  // ── 최근 대표 PR (단일 IR 아키텍처 완성 + 초급 트랙) ─────────
  recentPrs: [
    { num: 156, title: "QA 리뷰어 모델 Haiku→Sonnet 승급", type: "feat", impact: "최종 품질 게이트 정성판단 강화" },
    { num: 157, title: "알고리즘 분류를 problems 1급 컬럼으로 승격 (DB 스키마)", type: "feat", impact: "은행 분류·조회 1급화" },
    { num: 158, title: "QA-fix remediation — fail_qa 지문 수정→재리뷰 (재생성 아님)", type: "feat", impact: "QA 실패 저비용 구제 경로" },
    { num: 159, title: "도메인 팔레트 — banking 100% 단일화를 결정적 회전 분산", type: "feat", impact: "도메인 다양성 (leakage 방어, #152 동형)" },
    { num: 160, title: "쉬운 문제 적재 브리지 + 풀 채점셋 확장 (canonical/hybrid ingest)", type: "feat", impact: "문제 은행 적재 경로 확장" },
    { num: 161, title: "난이도 판별 에이전트 — RFC R4 BOJ 티어 calibration", type: "feat", impact: "별도 트랙(R4) 난이도 보정 착수" },
    { num: 162, title: "난이도 anchor 확장 — solved.ac 실측 20티어 (Bronze~Platinum)", type: "feat", impact: "R4 난이도 보정 실측 anchor" },
    { num: 163, title: "3세대 → 2 파이프라인 수렴 — v0 제거 + v1 prune", type: "refactor", impact: "레거시 정리 — v1 canonical + v2 fresh 2축" },
    { num: 164, title: "P1/P2 2-모드 수렴 — composition_mode + qa_kinds + 진입점 mode 선택", type: "feat", impact: "p1=단일·공개·QA3 / p2=합성·은닉·QA4 단일 노브" },
    { num: 165, title: "계약 v2.0 동기화 — mode p1/p2 breaking + difficulty/algorithm 컬럼", type: "docs", impact: "백엔드 계약 major 갱신 + 변경이력" },
    { num: 166, title: "알고리즘 분류 N:M 정션 — problems.algorithm → problem_algorithms", type: "feat", impact: "백엔드 필터링이 합성 기법까지 (계약 v3.0)" },
    { num: 167, title: "공개 검색 번호 problem_number — UUID 별도 사람용 핸들", type: "feat", impact: "검색·노출용 공개 번호 (계약 v3.1)" },
    { num: 168, title: "백엔드 공유 문서 재정리 — §6 구현상태 현행화 + 헤더/스키마 정리", type: "docs", impact: "핸드오프 readiness 정확화" },
    { num: 169, title: "authoring 정합성 수선 — P1 출하율 1/9→6/9 + 단일 IR RFC", type: "feat", impact: "P1 출하율 11%→67% 실측 회복" },
    { num: 170, title: "구조 IR 필드 GraphShape/indexing — F6~F8 단일 진실원천 (Phase 1)", type: "feat", impact: "단일 ProblemIR 인프라 — 모순 표면 축소" },
    { num: 171, title: "formalizer graph_shape EMIT + narrative/faithfulness 구조사실 검증 (Phase 1b)", type: "feat", impact: "F8 폐쇄 — 구조 사실 단일화" },
    { num: 172, title: "단일-IR 아키텍처 (Phase 2~5a) + 백본 일반화 (G0~G2)", type: "feat", impact: "IR validator + 순수투영 — 모순표면 O(N²)→O(2)" },
    { num: 174, title: "초급 문제 트랙 — seed-파생 난이도 + difficulty 완화 + abstract orthogonal", type: "feat", impact: "쉬운 문제 생성 트랙 확장" },
    { num: 175, title: "sequence write-side N=0/sortedness 단일소스화 — 'N=0↔constraints' 모순 해소", type: "fix", impact: "sequence 정합성 단일소스" },
  ],

  // ── 후속 / 별도 트랙 (추적용) ─────────────────────────────────────
  backlog: [
    { id: "출하율 재측정 (P1/P2)", priority: "후속", desc: "단일-IR 아키텍처(Phase 2~5a, #172) + sequence 모순해소(#175) 후 P1/P2 출하율 N≥3 재측정 — IR validator 가 P2 합성 ill-posed 를 구조적으로 차단" },
    { id: "백엔드 연동 핸드오프",  priority: "대기",     desc: "계약 v3.1(mode p1/p2 + difficulty + algorithm 정션 + problem_number) 공유 repo 송부 — 파이프라인측 정비 완료, 백엔드 소비 대기" },
    { id: "leakage corpus (Q2)",   priority: "품질",     desc: "유출 정량화 코퍼스 — composition/도메인 회전 팔레트 효과를 수치로 측정" },
    { id: "anchor Diamond·Ruby 확장", priority: "조건부", desc: "고난도 문제 생성 시 solved.ac anchor 를 Platinum 위로 확장 (현 Bronze~Platinum 20티어)" },
    { id: "algorithm 카테고리 차원 테이블", priority: "YAGNI", desc: "분류 카테고리(그래프/DP/...) 차원 테이블 — 현재는 정션만, 필요 시 도입" },
    { id: "Multi-lang 솔루션",      priority: "v2.x",     desc: "C++ / Go / Rust — _write_source 분기 추가" },
  ],

  // ── 핵심 원칙 (PRINCIPLES.md) ─────────────────────────────────────
  principles: [
    { icon: "📏", title: "측정 우선", desc: "N≥3 측정 + baseline anchor 없이는 머지하지 않는다. 추가 측정이 diminishing returns 면 중단하고 freeze." },
    { icon: "🧭", title: "해자 사수", desc: "재공사해도 typed artifact 계약 + 결정론적 검증 anchor 는 사수. 검증 path 는 절대 끊지 않는다." },
    { icon: "🪢", title: "복잡도 규율", desc: "그래프는 ≤6 스테이지, 모든 노드는 typed artifact + structured log emit, 병렬은 반드시 deterministic aggregator 로 fan-in." },
    { icon: "💸", title: "비용 규율",   desc: "모델 tiering 강제 (검증·집계는 코드 = 비용 0, Opus 는 Formalizer·Golden 등 정확성 임계에만). 단 QA 최종 게이트는 품질 우선으로 Sonnet 승급(#156). 1 run 실측 $0.4~0.6." },
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
    { id: "NFR-6",  title: "테스트 품질", metric: "v1 515 + v2 347 collected, coverage 87% (ipe/v1), mypy --strict 0 · ruff 0" },
    { id: "NFR-7",  title: "비용 효율",   metric: "1 run 실측 $0.4~0.6 (백엔드 계약 §5), list price 대비 ≈0.4x (Tier+cache)" },
    { id: "NFR-8",  title: "관측성",      metric: "LLM trace + replay + outputs/ 영속화 + LangSmith/OTel 옵션" },
    { id: "NFR-9",  title: "운영성",      metric: "make install / ipe CLI / resume·replay / measurement runner / 관리 콘솔" },
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
      { name: "pytest", version: "≥8.0.0", note: "테스트 러너 — v1 515 + v2 347 collected" },
      { name: "pytest-mock", version: "≥3.12.0", note: "LLM mock" },
      { name: "pytest-cov", version: "≥4.1.0", note: "coverage 87% (ipe/v1)" },
      { name: "ruff", version: "≥0.5.0", note: "lint (E/F/W/I/N/UP/B/C4/SIM) — 0 errors" },
      { name: "mypy", version: "≥1.10.0", note: "--strict 0 errors" },
    ],
    other: [
      { name: "pydantic", version: "≥2.0.0", note: "typed artifact 노드 계약 (v1 D안 도입)" },
      { name: "python-dotenv", version: "≥1.0.0", note: ".env 환경 변수" },
      { name: "jsonschema", version: "≥4.20.0", note: "LLM 출력 schema 검증" },
      { name: "fastapi", version: "≥0.115", note: "HTTP delivery layer — generate/jobs/healthz (B2C 계약, #144)" },
      { name: "uvicorn", version: "≥0.30", note: "ASGI 서버 — Dockerfile.api 컨테이너 배포 (#145)" },
      { name: "sqlalchemy", version: "≥2.0", note: "공유 PostgreSQL 영속화 — 문제 은행 직접 적재 + alembic migration 0005 (#150·#166·#167)" },
      { name: "psycopg", version: "[binary] ≥3.1", note: "PostgreSQL 드라이버 (SQLAlchemy Core) + advisory-lock 채번" },
    ],
  },

  // ── 제외 기술 + 이유 ──────────────────────────────────────────────
  exclusions: [
    { tech: "OpenAI SDK", reason: "Anthropic 단일 provider (langchain-anthropic 으로 충분)" },
    { tech: "Flask / Django", reason: "HTTP delivery 는 FastAPI 채택 (#144~145) — 경량 ASGI + Pydantic 계약 정합. Flask/Django 는 과함" },
    { tech: "Celery / Redis", reason: "단일 사용자/run — 큐 불필요" },
    { tech: "ORM-heavy 프레임워크 (Django ORM 등)", reason: "공유 PostgreSQL 영속화는 채택(#150, SQLAlchemy Core + psycopg) — 단 경량 사용. 풀 ORM 스택은 과함" },
    { tech: "TypedDict", reason: "v1 D안에서 Pydantic v2 typed artifact 로 전환 — 검증·계약 강화" },
    { tech: "Black + isort", reason: "ruff 통합 (single-tool 정책)" },
    { tech: "Poetry / Hatch", reason: "setuptools + requirements.txt 로 충분" },
  ],
};
