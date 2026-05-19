# IPE — Infinite Problem Engine

> 알고리즘 문제 자동 생성 파이프라인. **LangGraph + Claude**로 문제 설계 → 정해 작성 → 적대적 엣지케이스 → 시드 기반 stress test → 난이도 사후 평가까지 자동화.

[![Status](https://img.shields.io/badge/status-v0.2.1-brightgreen)](CHANGES.md)
[![Tests](https://img.shields.io/badge/tests-247%20passed-brightgreen)](tests/)
[![e2e](https://img.shields.io/badge/e2e-4%2F5%20success-brightgreen)](docs/improvements/2026-05-14_sandbox-infra-rca.md)
[![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen)](https://github.com/LsMin124/IPE/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Sandbox](https://img.shields.io/badge/sandbox-Docker%2Fnsjail%2Fsandbox--exec-brightgreen)](docs/dev/PROJECT_SPEC.md#451-sandboxing--resource-limits)

> 🌐 **인터랙티브 사이트**: [lsmin124.github.io/IPE](https://lsmin124.github.io/IPE/) — 시각화 대시보드 + 요구사항 + 기술 스택 (GitHub Pages 활성화 후 접근)

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
**제출용 / 진입점 (루트)**

| 문서 | 역할 |
|---|---|
| [`README.md`](README.md) | 본 문서 — 진입점 + 진행 상태 |
| [`REQUIREMENTS.md`](REQUIREMENTS.md) | 기능적/비기능적 요구사항 정의서 (제출용) |
| [`TECH_STACK.md`](TECH_STACK.md) | MVP 구현·운영 기술 스택 카탈로그 (제출용) |
| [`CHANGES.md`](CHANGES.md) | 변경 이력 (Round 1~9, v0.1.0~v0.2.0 진행) |

**에이전트 구현 참고 (`docs/dev/`)** — 구현 시 SSOT

| 문서 | 역할 |
|---|---|
| [`docs/dev/PROJECT_SPEC.md`](docs/dev/PROJECT_SPEC.md) | 요구사항·결정사항 (SSOT) |
| [`docs/dev/ARCHITECTURE.md`](docs/dev/ARCHITECTURE.md) | 모듈별 코드 설계 + 운영 가드레일 |
| [`docs/dev/IMPLEMENTATION_ROADMAP.md`](docs/dev/IMPLEMENTATION_ROADMAP.md) | 12-phase 구현 로드맵 (planner-grade) |
| [`docs/dev/PYTHON_GUIDE.md`](docs/dev/PYTHON_GUIDE.md) | Python/LangGraph 문법·관용구 참고 |

**진단·운영 (`docs/improvements/`, `docs/backlog/`)**

| 문서 | 역할 |
|---|---|
| [`docs/improvements/`](docs/improvements/) | RCA + troubleshooting playbook (Sprint 1~3 진행 기록) |
| [`docs/backlog/`](docs/backlog/) | phase audit + post-phase 미해소 항목 |
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

# 4. (선택) pre-commit hooks — git commit 시 ruff 자동 실행
pre-commit install
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

| Phase | 상태 | 완료 PR |
|---|---|---|
| **P0** Bootstrap | ✅ | `83e6bbf` |
| **P1** Sandbox Foundation | ✅ | `3f8d7bb` |
| **P2** LLM Layer | ✅ | PR #1 |
| **P3** Coder + Executor 최소회로 | ✅ | PR #2 |
| **P4** Architect + Phase A 라우팅 | ✅ | PR #4 |
| **P5** Auditor + Phase B | ✅ | PR #5 |
| **P6** Generator + Phase C | ✅ | PR #7 |
| **P7** Routing & Retry Discipline | ✅ | PR #9 |
| **P8** Checkpointing & Replay | ✅ | PR #11 |
| **P9** Evaluator + Calibration | ✅ | PR #13 |
| **P10** Output Persistence | ✅ | PR #15 |
| **P11** Observability | ✅ | PR #17 |
| **P12** Tests + CLI + CI | ✅ | PR #19 + audit #20 |
| **🎉 v0.1.0 Release** | ✅ | tag `v0.1.0` (main `77fb596`) |
| **🚀 v0.1.1 Patch** | ✅ | polish round 3 (B2 + sandbox CLI + F4) — tag `v0.1.1` |
| **🧪 v0.2.0 Sprint 1-3** | ✅ | R1/R4/R6/R10/R11/R13/R15 + R-sandbox (Run 9 3/5) |
| **🎉 v0.2.0 Release** | ✅ | Sprint 4 (R14 + R3 + R-bfs) — e2e **4/5 stable** (Run 11/12) — tag `v0.2.0` |
| **🎯 v0.2.1 Release** | ✅ | Round 11~18: 결정적 fix 9종 (oscillation breakers + sig granularity + infra fixes + retry/parse fallback) — SegTree 0/4 → success 직접 확인. tag `v0.2.1` |

상세 phase 정의·DoD: [`docs/dev/IMPLEMENTATION_ROADMAP.md`](docs/dev/IMPLEMENTATION_ROADMAP.md)

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

스키마 상세: [`docs/dev/PROJECT_SPEC.md` §6](docs/dev/PROJECT_SPEC.md#6-산출물-구조-polygon-style)

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

## Troubleshooting

### `ANTHROPIC_API_KEY` 미설정
```
KeyError: 'ANTHROPIC_API_KEY'
```
→ `.env` 파일 확인 (`cp .env.example .env` 후 키 입력).

### Sandbox tier 자동 선택 실패
```
RuntimeError: no usable sandbox tier
```
→ `make selftest-all` 로 각 tier 진단. T1(Docker)이 unavailable이면
T2.5(macOS sandbox-exec) 또는 T3(rlimit)으로 fallback. `--sandbox rlimit` 강제 가능.

### Resume / Replay 실패
```
checkpoint not found: outputs/<run_id>/checkpoint.db
```
→ `outputs/` 디렉토리에 `<run_id>` 존재 확인. P8 SqliteSaver 미통과 (예: 첫
super-step 전 abort) 시 재개 불가 — 새 run으로 시작.

### Cost guard 즉시 트리거
```
final_status: cost_exceeded
```
→ `--max-cost-usd` 너무 작거나 architect/coder가 large prompt를 사용 중.
default `5.0` USD에서 시작, 필요 시 증감.

### `mypy --strict` 실패
- 새 노드 추가 시 모든 함수 시그니처에 type annotation 필수.
- LangGraph node는 `(state) -> ProblemState` 형태로 반환 타입 명시.

상세 운영 가이드: [`docs/dev/ARCHITECTURE.md` §7-10](docs/dev/ARCHITECTURE.md)

---

## 라이선스

(미정 — P12 결정 보류)
