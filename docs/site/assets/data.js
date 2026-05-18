/* IPE site — shared data for all pages
 * RCA / CHANGES / playbook의 데이터를 inline JS 상수로 노출.
 * 모든 페이지에서 import 없이 window 전역으로 접근.
 */

window.IPE_DATA = {
  meta: {
    version: "v0.2.0 + Round 11~15",
    repo: "https://github.com/LsMin124/IPE",
    mainCommit: "3c3bccd",
    updated: "2026-05-18",
    e2eSuccess: "4/5 + Round 15 R-docker-workdir (Docker 인프라 fix — Round 11~13 효과 측정 가능해짐)",
    tests: 321,
    coverage: 93,
    nodes: 6,
    deps: 11,
  },

  // 7 PR (대표) — 자세한 시퀀스는 CHANGES.md
  recentPrs: [
    { num: 38, title: "R-sandbox PHASE_C_WORKERS=1", type: "fix", impact: "Run 9 3/5 (인프라 race 결정적 차단)" },
    { num: 40, title: "R14 PR 1 fanout opt-in", type: "feat", impact: "구조" },
    { num: 41, title: "R14 PR 2 best 선택", type: "feat", impact: "Run 10 4/5 (BFS 회복)" },
    { num: 45, title: "R3 Generator N+M 가이드", type: "feat", impact: "Run 11 4/5 (Segment Tree 회복)" },
    { num: 46, title: "R-bfs architect budget 4", type: "fix", impact: "Run 12 4/5 (BFS 재회복)" },
    { num: 47, title: "docs/dev/ 재구성", type: "docs", impact: "문서 일관성" },
    { num: 48, title: "v0.2.0 release prep", type: "docs", impact: "release tag" },
  ],

  // 6 LangGraph nodes
  graphNodes: [
    { id: "architect", label: "Architect", desc: "문제 설계 + structured constraints + samples" },
    { id: "coder", label: "Coder", desc: "정해(golden) + brute solution + LESSON + N-fanout" },
    { id: "auditor", label: "Auditor", desc: "8 adversarial inputs + syntactic validator" },
    { id: "generator", label: "Generator", desc: "5 generator scripts (4 categories) + seed" },
    { id: "executor", label: "Executor", desc: "3-Phase 검증 + brute cross-check + sandbox" },
    { id: "evaluator", label: "Evaluator", desc: "calibration anchor + 난이도 사후 평가" },
  ],

  // 5 e2e cases
  e2eCases: ["Two Sum", "BFS", "Dijkstra", "Segment Tree", "LIS"],

  // Run 1 ~ Run 12 매트릭스 (각 case 1=success, 0=fail, null=aborted)
  e2eRuns: [
    { run: 1,  label: "v0.1.1 baseline",       results: [0,0,0,0,0], total: "0/5", durMin: 11.3 },
    { run: 2,  label: "budget↑",               results: [0,0,0,0,0], total: "0/5", durMin: 9.0 },
    { run: 3,  label: "Sprint 1 (R1+R4)",      results: [0,0,0,0,0], total: "0/5", durMin: 10.2 },
    { run: 4,  label: "Sprint 1.5 (R11)",      results: [0,0,0,0,0], total: "0/5", durMin: 10.8 },
    { run: 5,  label: "max_iter=10",           results: [0,1,0,0,0], total: "1/5", durMin: 8.5 },
    { run: 6,  label: "Sprint 2 (R10) — hang", results: [null,null,null,null,null], total: "aborted", durMin: null },
    { run: 7,  label: "Sprint 2 (R10) retry",  results: [0,0,0,0,1], total: "1/5", durMin: 9.7 },
    { run: 8,  label: "Sprint 3 R13",          results: [0,0,0,0,0], total: "0/5", durMin: 9.0 },
    { run: 9,  label: "R-sandbox (PHASE_C=1)", results: [1,0,1,0,1], total: "3/5", durMin: 10.4 },
    { run: 10, label: "Sprint 4 R14 fanout=3", results: [1,1,1,0,1], total: "4/5", durMin: 18.6 },
    { run: 11, label: "Sprint 4 R3",           results: [1,0,1,1,1], total: "4/5", durMin: 12.4 },
    { run: 12, label: "Sprint 4 R-bfs",        results: [1,1,1,0,1], total: "4/5", durMin: 12.9 },
  ],

  // FR (기능 요구사항)
  fr: [
    { id: "FR-1",  title: "문제 자동 생성 (Architect)",      desc: "algorithm 키워드 → storytelling + structured constraints + 3-5 sample testcases" },
    { id: "FR-2",  title: "정해 작성 (Coder)",               desc: "Best-of-N fanout / LESSON 누적 / brute solution 동시 작성" },
    { id: "FR-3",  title: "적대적 입력 (Auditor)",           desc: "8 adversarial + syntactic validator" },
    { id: "FR-4",  title: "Stress Test (Generator)",         desc: "5 script × seed, R10 cap 2MB, 카테고리별 N 가이드" },
    { id: "FR-5",  title: "3-Phase 검증 (Executor)",         desc: "Phase A sample / B adversarial / C stress + brute cross-check" },
    { id: "FR-6",  title: "난이도 평가 (Evaluator)",         desc: "calibration anchor 기반 사후 평가" },
    { id: "FR-7",  title: "4-Tier Sandbox",                  desc: "Docker / nsjail / sandbox-exec / RLIMIT 자동 선택" },
    { id: "FR-8",  title: "Resume & Replay",                 desc: "SqliteSaver checkpoint + LLM trace 0-cost 재현" },
    { id: "FR-9",  title: "비용 가드",                       desc: "max_cost_usd 초과 시 halt, LLMCallTracker" },
    { id: "FR-10", title: "관측성 (LLM trace)",              desc: "raw input/output 디스크 저장 + 옵션 LangSmith/OTel" },
    { id: "FR-11", title: "산출물 영속화",                   desc: "problem.json + problem.md + tests/NN.{in,out}" },
    { id: "FR-12", title: "반복 제어",                       desc: "max_iter + per-node budget + cost guard 3중" },
    { id: "FR-13", title: "Oscillation 감지 (W4)",           desc: "동일 signature 2회+ 강한 경고 + R-bfs budget 흡수" },
    { id: "FR-14", title: "다언어 솔루션",                   desc: "Python / Java (C++/Go 후속)" },
  ],

  // NFR (비기능)
  nfr: [
    { id: "NFR-1",  title: "성능",         metric: "단일 문제 평균 < 10분, Phase C 정해 ≤ 50% time_limit" },
    { id: "NFR-2",  title: "안정성",       metric: "Sandbox 격리 + checkpoint resume + race 0 (PHASE_C_WORKERS=1)" },
    { id: "NFR-3",  title: "보안",         metric: "API key .env / 코드 sandbox / network 차단 (T1)" },
    { id: "NFR-4",  title: "확장성",       metric: "언어 추가 3 함수 분기 / 모델 PRICING table" },
    { id: "NFR-5",  title: "유지보수성",   metric: "파일 ≤ 800 lines, mypy --strict 0, ruff 0" },
    { id: "NFR-6",  title: "테스트 품질",  metric: "247 passed, coverage 93%, e2e 5 cases (DoD 4+)" },
    { id: "NFR-7",  title: "비용 효율",    metric: "list price upper bound, 실제 청구 ≈ 0.4x (Tier+cache)" },
    { id: "NFR-8",  title: "관측성",       metric: "LLM trace + replay + LangSmith/OTel 옵션" },
    { id: "NFR-9",  title: "운영성",       metric: "make install / ipe CLI / resume·replay / selftest-all" },
    { id: "NFR-10", title: "재현성",       metric: "seed-deterministic generator + replay 100%" },
  ],

  // Tech stack (간략 — TECH_STACK.md 그대로 미러)
  stack: {
    runtime: [
      { name: "Python", version: "3.11+", note: "TypedDict total=False + asyncio task group" },
      { name: "Java", version: "17 Temurin", note: "옵션 — Java 솔루션 시" },
    ],
    llm: [
      { name: "langgraph", version: "≥0.2.0", note: "노드 그래프 오케스트레이션" },
      { name: "langgraph-checkpoint-sqlite", version: "≥3.0.0", note: "SqliteSaver" },
      { name: "langchain-anthropic", version: "≥0.2.0", note: "ChatAnthropic wrapper" },
      { name: "anthropic", version: "≥0.40.0", note: "SDK" },
    ],
    sandbox: [
      { tier: "T1", name: "Docker", env: "all OS (daemon)", note: "Network 차단 + readonly mount + cgroup" },
      { tier: "T2", name: "nsjail", env: "Linux only", note: "namespace + seccomp + cgroup" },
      { tier: "T2.5", name: "sandbox-exec", env: "macOS only", note: "Apple Seatbelt" },
      { tier: "T3", name: "POSIX RLIMIT", env: "all OS (fallback)", note: "RLIMIT_AS/CPU/NPROC" },
    ],
    quality: [
      { name: "pytest", version: "≥8.0.0", note: "테스트 러너" },
      { name: "pytest-mock", version: "≥3.12.0", note: "LLM mock" },
      { name: "pytest-cov", version: "≥4.1.0", note: "coverage + threshold" },
      { name: "ruff", version: "≥0.5.0", note: "lint (E/F/W/I/N/UP/B/C4/SIM)" },
      { name: "mypy", version: "≥1.10.0", note: "--strict 0 errors" },
    ],
    other: [
      { name: "python-dotenv", version: "≥1.0.0", note: ".env 환경 변수" },
      { name: "jsonschema", version: "≥4.20.0", note: "LLM 출력 schema 검증" },
      { name: "setuptools", version: "≥64 + wheel", note: "build backend" },
    ],
  },

  // 제외 기술 + 이유
  exclusions: [
    { tech: "OpenAI SDK", reason: "Anthropic 단일 provider (langchain-anthropic으로 충분)" },
    { tech: "FastAPI / Flask", reason: "CLI tool — web layer 불필요" },
    { tech: "Celery / Redis", reason: "단일 사용자/run — 큐 불필요" },
    { tech: "PostgreSQL", reason: "출력 JSON 파일로 충분 (DB-insertable schema)" },
    { tech: "Pydantic", reason: "TypedDict + jsonschema로 충분, dep 비용 ↓" },
    { tech: "Black + isort", reason: "ruff 통합 (single-tool 정책)" },
    { tech: "Poetry / Hatch", reason: "setuptools + requirements.txt로 충분" },
  ],

  // Backlog (v0.2.2+) — Round 11에서 두 P0 모두 완료 (CHANGES §16.1, §16.2)
  backlog: [
    { id: "R5+", title: "Brute oracle Phase B 활용", priority: "P1", desc: "architect ↔ coder 라우팅 정확도 ↑" },
    { id: "R-sandbox v2", title: "ulimit wrapper로 PHASE_C_WORKERS=4 복귀", priority: "P3", desc: "Phase C 성능 회복" },
    { id: "Sub-agent", title: "Coder 분해 (Algorithm + Implementation)", priority: "v0.2.2", desc: "quality 미세 조정" },
    { id: "Multi-lang", title: "C++ / Go / Rust 솔루션", priority: "v0.3.0", desc: "_write_source 분기 추가" },
    { id: "FastAPI", title: "API화 + web UI", priority: "v0.4.0", desc: "다중 사용자" },
  ],

  // 완료된 결정적 fix (Round 11+) — dashboard에서 별도 섹션
  completedFixes: [
    {
      id: "R-osc-break",
      round: "Round 11",
      date: "2026-05-18",
      title: "Phase A oscillation breaker",
      desc: "architect signature 2회+ 시 coder 강제 라우팅 (라우팅 레벨 결정적 차단)",
      target: "BFS variance 2/4 → 결정적 차단",
      tests: 11,
      doc: "docs/improvements/2026-05-18_osc-break-deterministic.md",
    },
    {
      id: "R-gen-cap",
      round: "Round 11",
      date: "2026-05-18",
      title: "Generator hard cap validator",
      desc: "Generator 응답 직후 sandbox 실측으로 cap 초과 generator 사전 reject (Executor 진입 전 결정적 차단)",
      target: "Segment Tree 0/4 → 결정적 차단",
      tests: 9,
      doc: "docs/improvements/2026-05-18_gen-cap-deterministic.md",
    },
    {
      id: "R-coder-osc",
      round: "Round 12",
      date: "2026-05-18",
      title: "Coder oscillation breaker",
      desc: "coder가 동일 signature 2회+ 시 architect로 강제 라우팅 swap (helper 일반화: architect↔coder 대칭)",
      target: "Phase A coder 반복 fail (Docker BFS/SegTree 실측에서 발견)",
      tests: 11,
      doc: "docs/improvements/2026-05-18_coder-osc-deterministic.md",
    },
    {
      id: "R-sig-detail",
      round: "Round 13",
      date: "2026-05-18",
      title: "Phase A signature granularity",
      desc: "coder routing feedback에 실패 sample의 expected/actual prefix 포함 — 다른 problem이 같은 X/Y로 fail해도 sig 달라짐 (R-coder-osc effective fix)",
      target: "Round 12 SegTree에서 매 cycle oscillation_break 무의미 발동 패턴 해소",
      tests: 12,
      doc: "docs/improvements/2026-05-18_sig-detail.md",
    },
    {
      id: "R12",
      round: "Round 14",
      date: "2026-05-18",
      title: "Anthropic retry/backoff (운영 안정성)",
      desc: "LLM 호출에 HTTP status 기반 retryable 판별 + exponential backoff (2/4/8s, max 3). 529/429/timeout 등 일시 장애 자동 복구. 4xx client error는 즉시 raise.",
      target: "Round 12 BFS Docker run에서 발생한 Anthropic 529 Overloaded crash",
      tests: 13,
      doc: "docs/improvements/2026-05-18_r12-retry-resilience.md",
    },
    {
      id: "R-docker-workdir",
      round: "Round 15",
      date: "2026-05-18",
      title: "DockerRunner cwd 절대경로 fix (인프라)",
      desc: "DockerRunner.run()이 spec.cwd를 자동 절대화 (Path.resolve) + main.py도 OUTPUTS_ROOT/WORKDIR_ROOT를 .resolve(). R-sig-detail 덕분에 노출된 'docker working directory not absolute' 에러 해소.",
      target: "Round 14 e2e BFS/SegTree Docker 모든 sample RTE — sandbox 실행 자체 불가",
      tests: 7,
      doc: "docs/improvements/2026-05-18_docker-workdir-fix.md",
    },
  ],
};
