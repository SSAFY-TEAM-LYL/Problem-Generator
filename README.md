# IPE — Infinite Problem Engine

> 알고리즘 문제 자동 생성 파이프라인. **LangGraph + Claude**로 문제 설계 → 정해 작성 → 적대적 엣지케이스 → 시드 기반 stress test → 난이도 사후 평가까지 자동화.

[![Status](https://img.shields.io/badge/status-WIP-yellow)](IMPLEMENTATION_ROADMAP.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Sandbox](https://img.shields.io/badge/sandbox-Docker%2Fnsjail%2Fsandbox--exec-brightgreen)](PROJECT_SPEC.md#451-sandboxing--resource-limits)

---

## 개요

IPE는 외부 문제 소스에 의존하지 않고 고품질 알고리즘 문제(SWEA B형, 백준 골드 수준 포함)를 **자체 생산**하는 파이프라인이다. 6개의 LangGraph 노드 (Architect / Coder / Auditor / Generator / Executor / Evaluator) 가 **단일 `ProblemState`** 를 주고받으며 점진적으로 문제를 완성한다.

**핵심 원칙**
- **Sandboxed Local Execution** — LLM 생성 코드는 격리된 환경에서만 실행 (Docker / nsjail / sandbox-exec / RLIMIT 4-tier)
- **Resumable & Observable** — LangGraph SqliteSaver checkpointing + 모든 LLM 호출의 raw trace 보존
- **Bounded** — `max_iter` (안전망) + per-node retry budget (정밀 제어) + `max_cost_usd` (비용 가드) 3중 제어
- **Post-Verification Difficulty Rating** — 난이도는 검증 후 사후 측정 (calibration anchor 동봉)

---

## 문서 인덱스

| 문서 | 역할 |
|---|---|
| [`PROJECT_SPEC.md`](PROJECT_SPEC.md) | 요구사항·결정사항 (SSOT) |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 모듈별 코드 설계 + 운영 가드레일 |
| [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) | 12-phase 구현 로드맵 (planner-grade) |
| [`PYTHON_GUIDE.md`](PYTHON_GUIDE.md) | Python/LangGraph 문법·관용구 참고 |
| [`CHANGES.md`](CHANGES.md) | 변경 이력 (Round 1~4) |
| [`archive/`](archive/) | 외부 리뷰 등 archival 문서 |

---

## Quick Start

### 사전 요구사항
- **Python 3.11+** — `brew install python@3.11` (macOS)
- **Anthropic API 키** — https://console.anthropic.com/
- (운영 권장) **Docker Desktop** — sandbox T1 사용 시

### 설치

```bash
# 1. venv 생성 + activate
python3.11 -m venv .venv
source .venv/bin/activate

# 2. 패키지 + dev deps install (editable)
make install
# 또는: pip install -e ".[dev]"

# 3. 환경 변수 셋업
cp .env.example .env
# .env를 열어 ANTHROPIC_API_KEY 입력
```

### 검증

```bash
make ci          # ruff + mypy + pytest (with coverage)
```

### 사용 (P4 이후 활성)

```bash
# 한 사이클 실행
ipe --algorithm "Two Sum" --language python --max-iter 5 --max-cost-usd 5.0

# resume from checkpoint
ipe --resume <run_id>

# replay (LLM 비용 0으로 재현)
ipe --replay <run_id>
```

---

## 현재 진행 상태

| Phase | 상태 | 완료 commit |
|---|---|---|
| **P0** Bootstrap | ✅ 완료 | `83e6bbf` |
| **P1** Sandbox Foundation | 진행 예정 | — |
| **P2** LLM Layer | 진행 예정 | — |
| P3 Coder + Executor 최소회로 | — | — |
| P4 Architect + Phase A 라우팅 | — | — |
| P5 Auditor + Phase B | — | — |
| P6 Generator + Phase C | — | — |
| P7 Routing & Retry Discipline | — | — |
| P8 Checkpointing & Replay | — | — |
| P9 Evaluator + Calibration | — | — |
| P10 Output Persistence | — | — |
| P11 Observability | — | — |
| P12 Tests + CLI + CI | — | — |

상세 phase 정의·DoD: [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md)

---

## 산출물 구조 (예정)

P10 완료 후:
```
outputs/<run_id>/
├─ problem.json          # DB-insertable
├─ problem.md            # 사람이 읽는 형태
├─ solution.{py,java}
├─ generators/<name>.py
├─ tests/NN.{in,out} + manifest.json
├─ llm_traces/<seq>_<node>.json
└─ checkpoint.db
outputs/by-name/<timestamp>_<algo>  → ../<run_id>   # 사람용 별칭
```

스키마 상세: [`PROJECT_SPEC.md` §6](PROJECT_SPEC.md#6-산출물-구조-polygon-style)

---

## 개발 워크플로

```bash
# 코드 변경 후
make lint        # ruff + mypy
make test        # pytest
make ci          # 둘 다

# clean
make clean       # build/cache 정리
```

[`Makefile`](Makefile) 의 모든 타겟: `make help`

---

## 라이선스

(미정 — P12에서 결정)
