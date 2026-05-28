# IPE — Infinite Problem Engine

> **알고리즘 문제 생성 + 결정론적 검증 파이프라인**. LangGraph + Claude 4.7
> Opus/Sonnet 으로 problem spec → algorithm design → code → symbolic verifier
> 4-node pipeline. 19 algorithm × 4 invariants 누적 catalog.

[![Status](https://img.shields.io/badge/status-v1.0%20D%EC%95%88%20Phase%202c%20(19%20algo)-blue)](CHANGES.md)
[![Tests](https://img.shields.io/badge/tests-405%20passed-brightgreen)](tests/)
[![e2e](https://img.shields.io/badge/Phase%202c%20(N=3%20x%2019)-47%2F57%20(82.5%25)-green)](docs/baseline/v1-phase-2c-N3-19algo.md)
[![Engaged](https://img.shields.io/badge/samples_engaged-100%25-brightgreen)](docs/baseline/v1-phase-2c-N3-19algo.md)
[![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen)](https://github.com/LsMin124/IPE/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)

> 🌐 인터랙티브 대시보드: [lsmin124.github.io/IPE](https://lsmin124.github.io/IPE/)

---

## 무엇

IPE 는 **알고리즘 문제 생성 + 결정론적 검증** 시스템:

```
target_algorithm  →  [architect → designer → coder → executor]  →  검증된 문제 + 코드
                       (Opus)     (Sonnet)   (Opus)   (verifier)
```

각 algorithm 의 **수학적 invariants** 를 코드로 결정론적 검증 (LLM judgment
와 독립된 anchor). 19 algorithm × 4 invariants = 76 invariants 누적.

### v0 → v1 D안 architecture 진화

| 시점 | run-level | 비고 |
|---|---|---|
| v0 single LLM baseline | 27% | 단일 LLM call 의 정확도 anchor |
| v1 Phase 1 (Dijkstra MVR) | 100% (3/3) | D안 architecture 시작 |
| v1 Phase 2a (5 algo) | 93.3% (14/15) | baseline + 4 algo |
| v1 Phase 2b (13 algo) | 87.2% (34/39) | +8 algo (Search/DS/DP/Sort/String/...) |
| **v1 Phase 2c (19 algo)** | **82.5% (47/57)** | **+6 algo (Graph/DS/DP) — current** |

**+55pp vs v0 baseline 유지 + 100% samples_engaged 달성**. catalog ×3.8 확장.

---

## 19 Algorithm Catalog (Phase 2c)

| family | algorithm | verifier 핵심 invariant |
|---|---|---|
| Graph | Dijkstra | Bellman-Ford cross-check (non-negative weight) |
| Graph | BFS | Floyd-Warshall cross-check (edge=1) |
| Graph | Topological Sort | edges_respect_order + Kahn DAG check |
| Graph | Bellman-Ford | Floyd-Warshall cross-check (negative weight) |
| Graph | Floyd-Warshall | V × Bellman-Ford cross-check (all-pairs) |
| Graph | Kruskal MST | Prim cross-check |
| Graph | Max Flow | brute min-cut (max-flow min-cut theorem) |
| Search | Binary Search | linear scan cross-check |
| Search | LIS | patience sort O(N log N) |
| Array | Two Sum | brute O(N²) pair enumeration |
| Sort | Sort cluster | Python `sorted()` |
| String | String Match cluster | brute O(NM) substring search |
| DS | Segment Tree | naive O(NQ) range sum |
| DS | Heap (Min-PQ) | sorted-list simulation |
| DS | Fenwick Tree (BIT) | naive prefix-sum |
| DSU | Union-Find | BFS over union edges |
| DP | Knapsack 0/1 | brute O(2^N) subset enum |
| DP | Coin Change | DP O(N*A) tabulation |
| NumTheory | Sieve of Eratosthenes | trial division O(N√N) |

---

## Quick Start

```bash
# 환경 설정
uv sync --extra dev

# .env 에 ANTHROPIC_API_KEY 설정
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# 단일 algorithm 문제 생성 (verbose 으로 spec/code 확인)
uv run python -m ipe.v1.main_v1 --algorithm dijkstra --max-iter 4 --verbose

# N=3 measurement (단일 algo)
uv run python -m ipe.v1.measurement \
  --algorithm knapsack --n 3 \
  --output docs/baseline/data/my-run.jsonl

# Phase 2c 19 algo × N=3 = 57 runs (Gate 측정)
uv run python -m ipe.v1.measurement \
  --phase-2c --n 3 \
  --output docs/baseline/data/phase-2c.jsonl
```

지원되는 `--algorithm` 값: `dijkstra` / `lis` / `segtree` / `two_sum` /
`bfs` / `binary_search` / `union_find` / `toposort` / `knapsack` / `sort` /
`string_match` / `max_flow` / `sieve` / `bellman_ford` / `floyd_warshall` /
`kruskal_mst` / `heap` / `fenwick` / `coin_change`

산출물: `docs/baseline/data/*.jsonl` (RunOutcome JSONL) — 각 line 에
`run_id, final_status, sample_pass_count, sample_total, samples_engaged,
invariant_violations[], blocking_signatures[], elapsed_seconds`.

---

## 아키텍처

```text
USER CLI
   ↓
initial_state (V1State, Pydantic v2 frozen)
   ↓
LangGraph pipeline:
  [architect (Opus)] → ProblemSpec
        ↓
  [designer (Sonnet)] → AlgorithmDesign (+ invariants[])
        ↓
  [coder (Opus)] → SolutionAttempt (Python code)
        ↓
  [executor (no LLM)] → 4-phase verification:
        ├ Phase A: subprocess run per sample
        ├ Phase B: SymbolicVerifier dispatch (19 verifier registry)
        ├ Phase C: StructuredFeedback build (failure_mode + target_node)
        └ Phase D: routing decision (loop or terminate)
   ↓
[record] → final V1State + JSONL outcome
```

자세한 visualization: [`docs/v1-pipeline-flow.md`](docs/v1-pipeline-flow.md).

---

## 문서 (SSOT)

| 위치 | 역할 |
|---|---|
| [`docs/SPEC.md`](docs/SPEC.md) | 기능/비기능 요구사항 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 모듈 설계 + Pydantic schema SSOT |
| [`docs/v1-pipeline-flow.md`](docs/v1-pipeline-flow.md) | v1 D안 ASCII pipeline 시각화 |
| [`docs/PRINCIPLES.md`](docs/PRINCIPLES.md) | 5 운영 룰 (N≥3 / cross-algo regression / baseline anchor / complexity budget / RCA rollback) |
| [`docs/baseline/`](docs/baseline/) | Measurement raw data + 보고서 (Phase 2a/2b/2c) |
| [`CHANGES.md`](CHANGES.md) | 변경 이력 (§1~§66+) |

---

## 가설 (H1/H2/H3) Evidence

- **H1 (structured routing)**: API error 0 / budget_exhausted 0 / typed
  feedback 으로 architect↔coder 라우팅 결정론적 (Phase 2c 47/57 runs 전부
  결정적 종료)
- **H2 (algorithm-specific verifier)**: **samples_engaged 100%** 유지 across
  19 algo. Verifier dispatch (LLM 독립) 가 sample-level 정답성 결정.
- **H3 (IterationContext multi-iter recovery)**: binary_search r1/r2 +
  segtree r1 + toposort retries 모두 iter=2 recover. fail_oscillation 은
  외부 routing 한계 (P3 후속).

---

## 개발

```bash
make ci             # ruff + mypy --strict + pytest
uv run pytest tests/v1 -q --ignore=tests/v1/test_e2e_real_llm.py
uv run python -m ipe.v1.main_v1 --algorithm sieve --max-iter 4 --verbose
```

자세한 운영 룰 → [`docs/PRINCIPLES.md`](docs/PRINCIPLES.md).

---

## 기여 / 알려진 이슈

- **Two Sum persistent fail**: architect 가 array 작성 시 multiple valid pair
  생성하는 경우 expected_output mismatch. P3 routing 확장 (sample_mismatch +
  invariant_violations=[] → architect back-route) 으로 systematic recovery
  계획.
- **outputs/ persistence**: v1 D안 은 RunOutcome metric 만 jsonl 저장. spec/
  code 영속화는 후속 (verbose flag 로 console 출력만).

PR 환영. [PRINCIPLES.md](docs/PRINCIPLES.md) 의 5 운영 룰 (N≥3 측정 / cross-algo
regression / baseline anchor / complexity budget / RCA rollback) 준수 권장.
