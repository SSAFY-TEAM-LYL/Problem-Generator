# IPE v1 D안 Pipeline — 전체 플로우 + 노드 + 산출물 시각화

> 2026-05-27 Phase 2b 완료 시점 기준. D안 architecture (Detection Backbone +
> State Refactor) 의 LangGraph 4-node pipeline + symbolic verifier dispatch.
>
> 본 문서는 시각화 중심. 텍스트 narrative 는 [ARCHITECTURE.md](./ARCHITECTURE.md),
> 측정 결과는 [baseline/v1-phase-2b-N3-13algo.md](./baseline/v1-phase-2b-N3-13algo.md).

## 1. 전체 플로우

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  USER ENTRY POINT                                                              │
│                                                                                │
│    $ python -m ipe.v1.main_v1 --algorithm dijkstra --max-iter 8               │
│    $ python -m ipe.v1.measurement --phase-2b --n 3 --output ...               │
└───────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  initial_state(run_id, target_algorithm: TargetAlgorithm, max_iterations=8)   │
│                                                                                │
│    V1State (Pydantic v2 frozen, extra=forbid)                                 │
│    ├─ run_id: str                       ├─ verification: None                 │
│    ├─ target_algorithm: TargetAlgorithm  ├─ context: IterationContext(empty) │
│    ├─ max_iterations: int                ├─ iteration: 0                      │
│    ├─ spec: None       (ProblemSpec)     └─ final_status: None                │
│    ├─ design: None     (AlgorithmDesign)                                      │
│    └─ attempt: None    (SolutionAttempt)                                      │
└───────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
              ┌──────────── build_graph() (LangGraph) ────────────┐
              │  StateGraph[V1State] compiled with checkpointing  │
              └────────────────────┬──────────────────────────────┘
                                   │
                                   ▼
  ╔════════════════════════════════════════════════════════════════════════════╗
  ║  ITERATION LOOP (iteration ∈ [0, max_iterations-1])                        ║
  ╚════════════════════════════════════════════════════════════════════════════╝
                                   │
        ┌──────────────────────────┴──────────────────────────┐
        │                                                       │
        ▼                                                       │
┌───────────────────────────────────────┐                       │
│  [1] architect node                    │                       │
│  ───────────────────────────────────   │                       │
│  LLM: Opus 4.7  (with_structured_output│                       │
│        + .with_retry(5, jitter))       │                       │
│  IN : V1State (+ prior feedback)       │                       │
│  OUT: ProblemSpec                      │                       │
│       ├ title, description             │                       │
│       ├ constraints[]                  │                       │
│       ├ io_contract                    │                       │
│       └ sample_testcases[3..5]         │                       │
└───────────────┬───────────────────────┘                       │
                │ ProblemSpec → state.spec                       │
                ▼                                                │
┌───────────────────────────────────────┐                       │
│  [2] designer node                     │                       │
│  ───────────────────────────────────   │                       │
│  LLM: Sonnet 4.6                       │                       │
│  IN : ProblemSpec (+ feedback)         │                       │
│  OUT: AlgorithmDesign                  │                       │
│       ├ algorithm_name                 │                       │
│       ├ pseudocode                     │                       │
│       ├ complexity_target (time/space) │                       │
│       ├ edge_cases[]                   │                       │
│       ├ data_structures[]              │                       │
│       └ invariants[] ◀── dispatch key  │                       │
└───────────────┬───────────────────────┘                       │
                │ AlgorithmDesign → state.design                 │
                ▼                                                │
┌───────────────────────────────────────┐                       │
│  [3] coder node                        │                       │
│  ───────────────────────────────────   │                       │
│  LLM: Opus 4.7                         │                       │
│  IN : ProblemSpec + AlgorithmDesign +  │                       │
│       feedback                         │                       │
│  OUT: SolutionAttempt                  │                       │
│       ├ code: str (Python source)      │                       │
│       └ iteration: int                 │                       │
└───────────────┬───────────────────────┘                       │
                │ SolutionAttempt → state.attempt                │
                ▼                                                │
┌───────────────────────────────────────────────────────────────┐│
│  [4] executor node                                             ││
│  ────────────────────────────────────────────                  ││
│  ☆ NO LLM — deterministic subprocess + symbolic verifier      ││
│                                                                ││
│  Phase A: run code subprocess for each sample                  ││
│           IN : SolutionAttempt.code + sample.input_text        ││
│           OUT: ExecutionResult per sample                      ││
│                ├ stdout, stderr                                ││
│                ├ exit_code, elapsed_ms                         ││
│                └ SampleResult(passed/mismatch/error)           ││
│                                                                ││
│  Phase B: dispatch SymbolicVerifier by spec.target_algorithm   ││
│           ┌────────────────────────────────────────────────┐  ││
│           │  registry: 13 verifier (Phase 2b)              │  ││
│           │  Dijkstra / LIS / SegTree / TwoSum / BFS       │  ││
│           │  BinarySearch / UnionFind / Toposort           │  ││
│           │  Knapsack / Sort / StringMatch / MaxFlow/Sieve │  ││
│           └────────────────────────────────────────────────┘  ││
│           IN : ProblemSpec + design + attempt + sample_outputs ││
│           OUT: InvariantViolation[] + samples_engaged count    ││
│                                                                ││
│  Phase C: build StructuredFeedback (failure_mode + target_node)││
│           ├ failure_mode ∈ {none, sample_mismatch,             ││
│           │                invariant_violation, code_error,    ││
│           │                timeout, ...}                       ││
│           ├ target_node ∈ {ARCHITECT, DESIGNER, CODER}         ││
│           ├ actionable_hint: str                               ││
│           └ blocking_signature: "sample-N-mismatch" etc        ││
│                                                                ││
│  OUT: VerificationResult → state.verification                  ││
└───────────────┬───────────────────────────────────────────────┘│
                │                                                 │
                ▼                                                 │
   ┌─────────── ROUTING (after_executor) ───────────┐            │
   │                                                  │            │
   │  if failure_mode == none:        → record (END) │            │
   │  if iteration >= max_iterations: → record (END) │            │
   │  if same blocking_sig ×2:        → record (END) │ ┐          │
   │     ↑ fail_oscillation                          │ │          │
   │  else: → feedback.target_node ──────────────────│─┘          │
   │     ├ ARCHITECT → loop back to [1]              │            │
   │     ├ DESIGNER  → loop back to [2]              │            │
   │     └ CODER     → loop back to [3]              │            │
   └─────────────────────────────────────────────────┘            │
                │                                                 │
                ▼                                                 │
                └─────────── continue loop ───────────────────────┘
                                   │
                                   ▼
                          ┌────────────────┐
                          │ [5] record node│
                          │  ─────────────  │
                          │  Final state    │
                          │  serialization  │
                          └────────┬───────┘
                                   │
                                   ▼
```

## 2. Terminal outputs

```
╔════════════════════════════════════════════════════════════════════════════════╗
║  TERMINAL OUTPUTS                                                              ║
╚════════════════════════════════════════════════════════════════════════════════╝
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
┌─────────────────┐    ┌──────────────────────┐    ┌────────────────────┐
│  V1State        │    │  RunOutcome           │    │  IterationContext  │
│  (final)        │    │  (JSONL line)         │    │  (per-iter log)    │
│  ─────────────  │    │  ──────────────────   │    │  ────────────────  │
│  final_status:  │    │  run_index            │    │  iterations[]:     │
│   ├ success     │    │  run_id               │    │   ├ node           │
│   ├ fail_       │    │  final_status         │    │   ├ failure_mode   │
│   │ oscillation │    │  iteration_used       │    │   ├ blocking_sig   │
│   ├ fail_max_   │    │  sample_pass_count    │    │   └ target_node    │
│   │ iter        │    │  sample_total         │    │                    │
│   └ api_error   │    │  samples_engaged      │    │  (H3 anchor:       │
│                 │    │  invariant_           │    │   skill amnesia    │
│  iteration: N   │    │   violations[]        │    │   완화 evidence)   │
│                 │    │  blocking_            │    │                    │
│  spec/design/   │    │   signatures[]        │    │                    │
│  attempt/       │    │  elapsed_seconds      │    │                    │
│  verification   │    │                       │    │                    │
└─────────────────┘    └──────────────────────┘    └────────────────────┘
        │                          │
        ▼                          ▼
┌────────────────────┐    ┌────────────────────────────────────────┐
│  console summary   │    │  docs/baseline/data/                    │
│  (main_v1)         │    │   v1-phase-2b-N3-13algo-detailed.jsonl │
│  ────────────────  │    │  (append per run)                       │
│  final_status=...  │    └────────────────────────────────────────┘
│  sample_results:   │
│   X/Y passed       │
│  iteration_history │
└────────────────────┘
```

## 3. Data flow summary

```
╔════════════════════════════════════════════════════════════════════════════════╗
║  DATA FLOW SUMMARY (Pydantic v2 typed artifacts, 모두 frozen + extra=forbid)   ║
╚════════════════════════════════════════════════════════════════════════════════╝

      User CLI  ──►  initial_state  ──►  V1State(empty)
                                            │
                                            ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                                                                  │
   │   architect ──ProblemSpec──►   ┌──────────────────────────┐    │
   │       (Opus 4.7)                │  state.spec              │    │
   │                                 ├──────────────────────────┤    │
   │   designer ──AlgorithmDesign─►  │  state.design            │    │
   │       (Sonnet 4.6)              ├──────────────────────────┤    │
   │                                 │  state.attempt           │    │
   │   coder ────SolutionAttempt──►  │  (Python code)           │    │
   │       (Opus 4.7)                ├──────────────────────────┤    │
   │                                 │  state.verification      │    │
   │   executor ─VerificationResult► │   ├ sample_results[]     │    │
   │       (no LLM)                  │   ├ invariant_violations │    │
   │   + symbolic verifier           │   ├ samples_engaged: int │    │
   │     (13 algo)                   │   └ feedback: Structured │    │
   │                                 │     ├ failure_mode       │    │
   │   router ──TargetNode──► loop   │     ├ target_node ◀━━━━━│━━━┐│
   │           or terminal           │     ├ actionable_hint    │   ││
   │                                 │     └ blocking_signature │   ││
   │                                 └──────────────────────────┘   ││
   │                                                                 ││
   └─────────────────────────────────────────────────────────────────┘│
                                                                       │
                  ┌──────── routes back to ────────────────────────────┘
                  │
                  ▼
              [architect | designer | coder] → loop
```

## 4. Phase 2b 실제 example — knapsack r2 (fail_oscillation)

```
╔════════════════════════════════════════════════════════════════════════════════╗
║  실제 PHASE 2B 측정 EXAMPLE — knapsack r2 (FAIL OSCILLATION)                   ║
╚════════════════════════════════════════════════════════════════════════════════╝

  iter=0:
    architect (Opus)    ──► spec (sample 0: "5 5\n2 3\n...", expected="9")  ⚠ wrong
    designer  (Sonnet)  ──► invariants: value_optimal_via_brute, ...
    coder     (Opus)    ──► code (correct DP)
    executor            ──► sample 0 actual="8", expected="9"
                            sample 1-3: pass
                            verifier value_optimal_via_brute: passes ("8"==brute)
                            ◀ invariant_violations=[]
                            ◀ feedback: failure_mode=sample_mismatch
                                        target_node=CODER         ◀ misroute
                                        blocking_sig="sample-0-mismatch"

  iter=1:
    coder retry         ──► code (similar correct DP)
    executor            ──► sample 0 actual="8" again (same!)
                            ◀ same blocking_sig="sample-0-mismatch"

  router: iter=2 + same sig ×2 → fail_oscillation → record (END)

  ┌────────────────────────────────────────────────────────────────────┐
  │ root cause: architect 의 expected_output 이 wrong, coder 는 정답.  │
  │ routing 한계: sample_mismatch 시 ARCHITECT 로 back-route 없음.    │
  │ ↑ knapsack outlier 1/3 의 모든 fail 이 이 패턴.                    │
  └────────────────────────────────────────────────────────────────────┘
```

## 관련 문서

- [ARCHITECTURE.md](./ARCHITECTURE.md) — D안 architecture narrative
- [SPEC.md](./SPEC.md) — typed schema (ProblemSpec, AlgorithmDesign, ...)
- [PRINCIPLES.md](./PRINCIPLES.md) — N≥3 측정 / cross-algo regression / baseline anchor 등 룰
- [baseline/v1-phase-2b-N3-13algo.md](./baseline/v1-phase-2b-N3-13algo.md) — 본 pipeline 의 Phase 2b 측정 결과
- [../CHANGES.md](../CHANGES.md) §47~§56 — Phase 1/2a/2b PR 누적 narrative
