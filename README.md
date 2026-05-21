# IPE — Infinite Problem Engine

> **검증된 알고리즘 문제 + audit-able 카탈로그**. LangGraph + Claude 로 문제 설계 →
> 정해 작성 → 적대적 엣지케이스 → stress test → 난이도 평가 → 사람 review → catalog.

[![Status](https://img.shields.io/badge/status-v0.3.0--rc1%20(release%20held)-yellow)](CHANGES.md)
[![Tests](https://img.shields.io/badge/tests-474%20passed-brightgreen)](tests/)
[![e2e](https://img.shields.io/badge/e2e%20(N=3)-3%2F15%20run--level%20%2F%2087.7%25%20sample--level-yellow)](docs/baseline/v0.3.0-rc1-N3.md)
[![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen)](https://github.com/LsMin124/IPE/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Sandbox](https://img.shields.io/badge/sandbox-Docker%2Fnsjail%2Fsandbox--exec-brightgreen)](docs/SPEC.md#45-실행-격리-sandbox-4-tier)

> 🌐 인터랙티브 사이트: [lsmin124.github.io/IPE](https://lsmin124.github.io/IPE/)

---

## 무엇

IPE 는 LLM 만으로 문제를 *생성* 하는 것이 아니라 **검증 + 격리 + 영속화 + 사람
review** 까지 묶은 파이프라인. 단일 LLM call 대비 정량 우위:

| Metric | 단일 LLM baseline | IPE | Δ |
|---|---|---|---|
| Run-level success | 27% (N=15) | 20% | -7pp |
| Sample-level pass | 78.7% | **87.7%** | **+9pp** |

→ IPE 의 가치는 *generation quality* 가 아니라 **verification + observability +
catalog** 에 있다. 자세한 분석은 [`docs/baseline/v0.3.0-rc1-N3.md`](docs/baseline/v0.3.0-rc1-N3.md)
+ [`docs/STRATEGIC_REVIEW`](docs/archive/2026-05_strategic-review.md).

핵심 가치:
- **4-tier sandbox** — LLM 코드 host 격리 (Docker / nsjail / sandbox-exec / RLIMIT)
- **Replay mode** — `ipe --replay <run_id>` cost 0 reproduction (audit-ability)
- **Catalog persistence** — 사람 review 통과 문제만 catalog promote
  ([`docs/catalog/SCHEMA.md`](docs/catalog/SCHEMA.md))
- **3-Phase verification** — sample / adversarial / stress + brute oracle

---

## Quick Start

```bash
# 설치
make install

# 새 문제 생성 (Two Sum, Python, Docker sandbox)
ipe --algorithm "Two Sum"

# 성공 시 catalog 에 자동 promote
ipe --algorithm "Two Sum" --promote-to-catalog

# 사람 review
python -m ipe.catalog list --status draft
python -m ipe.catalog show <id>
python -m ipe.catalog approve <id> --by minsu

# 단일 LLM baseline 측정 (PRINCIPLES.md §3)
python -m ipe.baseline batch
```

산출물: `outputs/<run_id>/{problem.json, problem.md, solution.py, tests/, llm_traces/, checkpoint.db}` + `outputs/catalog/problems.jsonl`.

---

## 문서 (SSOT 5개)

| 위치 | 역할 |
|---|---|
| [`docs/SPEC.md`](docs/SPEC.md) | 기능/비기능 요구사항 + 기술 스택 + 인수 기준 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 모듈 설계 + 그래프 토폴로지 + schema SSOT |
| [`docs/PRINCIPLES.md`](docs/PRINCIPLES.md) | 5 운영 룰 (N≥3 measurement / cross-algo regression / baseline anchor / complexity budget / RCA rollback) |
| [`docs/catalog/SCHEMA.md`](docs/catalog/SCHEMA.md) | Catalog JSONL schema + 백엔드 활용 |
| [`CHANGES.md`](CHANGES.md) | 변경 이력 (Round 1~23 + RFC + Catalog + Baseline) |

기타: [`docs/improvements/`](docs/improvements/) (통합 RCA 5 + 단독 3) · [`docs/baseline/`](docs/baseline/) (measurement raw + 보고서) · [`docs/archive/`](docs/archive/) (한시 문서 + 원본 RCA + RFC + backlog)

---

## v0.3.0 release 상태 (보류)

PRINCIPLES.md §3 결정 트리:
- baseline ≈ IPE (|Δ run| < 20pp) → IPE 는 검증 layer 만 정당화
- **다음 PR**: M3 dual-call rollback (Dijkstra baseline 3/3 vs IPE 0/3 명백한 음효과)
- 그 후 v0.3.0 재측정 + tag

---

## 개발

```bash
make ci             # ruff + mypy --strict + pytest
make selftest-all   # sandbox isolation 4-tier 자가진단
make clean
```

자세한 dev workflow + 운영 룰 → [`docs/PRINCIPLES.md`](docs/PRINCIPLES.md).
