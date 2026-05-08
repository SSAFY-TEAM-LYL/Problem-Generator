# IPE 프로젝트 문서 종합 분석 보고서

> **리뷰어:** Antigravity (architect + code-reviewer 역할)  
> **대상 문서:**
> - `PROJECT_SPEC.md` — 434줄, 28KB
> - `ARCHITECTURE.md` — 1486줄, 69KB
> - `CHANGES.md` — 152줄, 8.5KB
> 
> **일시:** 2026-05-07

---

## 1. 문서 간 관계 및 역할 매핑

```
PROJECT_SPEC.md ──────── "무엇을 만들 것인가" (요구사항 + 제약)
        │
        │ 상세 구현 지침
        ▼
ARCHITECTURE.md ──────── "어떻게 만들 것인가" (코드 구조 + 문법 가이드)
        ▲
        │ 변경 요약
CHANGES.md ───────────── "무엇이 바뀌었는가" (보강 이력)
```

| 문서 | 본래 목적 | 현재 상태 |
|------|-----------|-----------|
| PROJECT_SPEC | MVP 요구사항 정의 | ✅ 완성도 높음. P0~P2 scope 분류까지 포함. |
| ARCHITECTURE | 코드 구조 + Python 문법 교육 가이드 | ⚠️ 하이브리드 — 구현 가이드와 교육 자료가 혼재. |
| CHANGES | 보강 이력 추적 | ✅ 변경점 명확. 미해결 이슈 4건 기록. |

---

## 2. 설계 강점 (유지해야 할 핵심 자산)

### 2.1 사후 난이도 평가 + Calibration Anchor

> LLM에게 "골드 난이도를 만들어라"고 지시하는 것은 프롬프트 엔지니어링의 가장 흔한 실수 중 하나입니다.

- **사전 지정 대신 사후 측정**: 문제를 자유롭게 생성 → 검증 통과 → 이후 별도 에이전트가 평가.
- **Calibration anchor set**: 백준 표준 난이도별 reference 문제를 few-shot으로 동봉하여 run-to-run 분산 축소.
- 이 설계는 **반드시 유지**해야 합니다.

### 2.2 3-Phase 결정론적 검증 (Executor)

| Phase | Oracle 출처 | 검증 대상 |
|-------|-------------|-----------|
| A: Sample | Architect의 `expected_output` | 정확성 (exact match) |
| B: Adversarial | Golden Solution 출력 자체 | 견고성 (RTE/TLE 없음) |
| C: Stress | Golden Solution 출력 자체 | 성능 + 견고성 |

- LLM이 LLM을 검증하는 것이 아닌, **물리적 실행 결과**를 ground truth로 사용.
- Phase A의 휴리스틱 라우팅(다수 통과/소수 실패 → Architect vs Coder 분기)은 영리한 설계.

### 2.3 Generator (Codeforces Polygon 패턴)

- LLM이 테스트 **입력 데이터 자체**를 출력하지 않고, 데이터를 생성하는 **Python 스크립트**를 출력.
- 시드 고정 → 결정론적 재현. 비용 절감과 재현성을 동시에 확보.

### 2.4 다단계 가드레일 시스템

```
sandbox_isolation_fail → cost_exceeded → budget_exhausted → max_iterations → success
```

- 5중 termination 계층 (ARCH §9.5)은 프로덕션 수준의 방어 설계.
- per-node retry budget + 글로벌 max_iter 이중 제어.

---

## 3. 위험 요소 및 설계 결함

### 🔴 CRITICAL — 문서 간 불일치 및 모순

#### 3.1 ARCHITECTURE.md의 `io.py`가 구 스키마를 참조

- `ARCHITECTURE.md` §3.11 (L1089): 여전히 `outputs/<timestamp>_<algo>/` 경로 사용.
- `PROJECT_SPEC.md` §6 (L311): `outputs/<run_id>/`로 변경됨.
- `CHANGES.md` (L124): "timestamp_algo는 별칭 심볼릭 링크"라고 명시했으나, ARCHITECTURE.md 본문에는 반영 안 됨.

#### 3.2 `problem.json` 스키마 이중 정의

- `ARCHITECTURE.md` §6 (L1303~L1361): **구** 스키마 — `meta`에 `run_id`, `sandbox_tier` 등 없음, `constraints_structured` 없음, `iteration_history` 없음, `llm_calls` 없음.
- `PROJECT_SPEC.md` §6 (L332~L380): **신** 스키마 — 모든 신규 필드 포함.
- **두 스키마가 충돌합니다.** CLI가 구현할 때 어느 쪽을 따라야 하는지 혼동 유발.

#### 3.3 Evaluator 코드 이중 정의

- `ARCHITECTURE.md` L983~L1011: 기본 Evaluator (`constraints_structured` 미사용, anchor 없음).
- `ARCHITECTURE.md` L1037~L1065: Calibration anchor 포함 Evaluator.
- **같은 파일 안에 같은 함수의 두 버전이 공존.** CLI 구현자가 어느 것을 따라야 하는지 불명확.

---

### 🟡 WARNING — 구현 시 병목/리스크

#### 3.4 macOS에서 Sandbox T2가 작동하지 않음

- `PROJECT_SPEC.md` L241: "Linux/macOS는 nsjail/firejail 우선 시도"
- **`nsjail`과 `firejail`은 Linux 전용입니다.** macOS에서는 동작하지 않음.
- macOS에서는 사실상 **T3(rlimit only)로 fallback**되며, 이 경우 네트워크/파일시스템 격리가 없음.
- 사용자의 현재 OS가 **macOS**이므로, MVP에서 T2는 사용 불가능합니다.

> ⚠️ macOS 환경에서 MVP를 개발/테스트한다면, 실질적 sandbox 선택지는 **T1(Docker)** 또는 **T3(rlimit fallback + 경고)** 뿐입니다.

#### 3.5 `constraints_structured` 파싱 실패 시 fallback 전략이 불완전

- Architect가 `constraints_structured`를 출력하지 않으면 → 글로벌 기본값(5초/512MB)으로 fallback → 재시도 강제.
- 그런데 **재시도 시에도 Architect가 같은 형태로 응답할 가능성이 높음** (프롬프트만으로는 구조화 출력 강제가 어려움).
- Anthropic의 `tool_use` / structured output 기능 사용 검토 필요.

#### 3.6 Phase A에서의 "유일한 외부 진실원" 취약점

- Architect의 `expected_output`이 잘못될 경우, 정답 코드가 오답으로 판정되어 Coder로 라우팅.
- Coder가 잘못된 expected_output에 맞추어 코드를 "수정"하면, **논리적으로 틀린 솔루션이 "통과"**될 수 있음.
- 현재의 휴리스틱 라우팅(다수 통과 + 소수 실패 → Architect)이 이를 부분적으로 완화하지만, **전체 sample이 잘못된 경우**는 방어 불가.

#### 3.7 `iteration_history`의 oscillation 방지 효과가 미검증

- SPEC은 oscillation_rate < 10%를 목표로 하지만, 실제로 LLM이 `iteration_history`를 프롬프트에 받았을 때 이전 실패를 회피하는지는 **실험적으로 검증되지 않았음**.
- 프롬프트에 history를 넣는 것만으로는 부족하고, 명시적으로 "이전 시도와 다른 접근법을 사용하라"는 지시가 필요할 수 있음.

---

### 🟢 MINOR — 문서 품질

#### 3.8 ARCHITECTURE.md의 교육 자료 혼재

- Python 문법 설명(§4, L1240~L1266), LangGraph 패턴 설명(§5, L1269~L1296), 흔한 실수(§7, L1373~L1381) 등이 아키텍처 문서에 포함.
- "Python에 익숙하지 않은 독자를 위한" 교육적 콘텐츠가 약 **400줄 이상**.
- 이 콘텐츠가 CLI(Claude Code)의 구현에 도움이 되는지, 아니면 노이즈인지 판단 필요.

#### 3.9 Claude 모델 버전명의 혼재

- SPEC과 ARCH 전체에서 `Claude Opus 4.7`, `Claude Sonnet 4.6` 등의 마케팅명이 사용됨.
- 실제 API 모델 ID는 `claude-opus-4-7`, `claude-sonnet-4-6` 등 (ARCH §3.3 L240~L243에 정의).
- 마케팅명과 API ID를 혼용하면 구현 시 혼란. **한 곳에서만 정의하고 나머지는 참조.**

---

## 4. 재기획 시 반드시 결정해야 할 질문

> ⚠️ 아래 질문들은 CLI(Claude Code)가 구현을 시작하기 전에 반드시 확정되어야 합니다.

### Q1. LangGraph를 유지할 것인가?

현재 설계는 `LangGraph`에 강하게 결합되어 있습니다 (StateGraph, SqliteSaver, conditional edges, recursion_limit 등).

| 선택 | 장점 | 단점 |
|------|------|------|
| **유지** | 상태 관리, 라우팅, checkpointing 이미 설계됨. 구현 빠름. | LangGraph 의존성 추가. ECC 생태계와 별개 동작. |
| **제거** | ECC `loop-operator` + agent orchestration으로 통합. | 상태 관리/체크포인팅을 직접 구현해야 함. |
| **하이브리드** | LangGraph 파이프라인 유지 + 각 노드의 LLM 호출을 CLI가 수행 (MCP 툴로 노출). | 복잡도 증가. |

### Q2. MVP의 타겟 OS는?

| 선택 | Sandbox 옵션 | 개발 난이도 |
|------|-------------|------------|
| macOS only | T1(Docker) 또는 T3(rlimit) | 중간 (Docker Desktop 필수 또는 보안 타협) |
| Linux only | T1/T2/T3 모두 가능 | 낮음 |
| Cross-platform | T1(Docker)을 기본으로 | 높음 (Docker Desktop 설치 강제) |

### Q3. `ARCHITECTURE.md`의 Python 교육 콘텐츠를 분리할 것인가?

- **현재:** 아키텍처 + 교육이 하나의 1486줄 문서에 혼재.
- **제안:** `ARCHITECTURE.md` (순수 설계, ~500줄) + `PYTHON_GUIDE.md` (문법/관용구 교육, ~400줄) 분리.
- CLI(Claude Code)에게는 교육 콘텐츠가 불필요. 오히려 컨텍스트 윈도우를 낭비.

### Q4. 문서를 단일 진실원(Single Source of Truth)으로 통합할 것인가?

현재 `problem.json` 스키마가 SPEC과 ARCH 양쪽에 정의되어 충돌합니다.
- **제안 A:** `PROJECT_SPEC.md`를 SSOT로 하고, `ARCHITECTURE.md`는 구현 세부사항만 다루되 스키마는 SPEC을 참조.
- **제안 B:** 별도 `SCHEMA.md` 파일로 분리.

### Q5. Retry Budget 기본값의 합리성

| Node | 현재 Budget | 잠재적 문제 |
|------|------------|------------|
| architect | 2 | 충분 (문제 지문 자체가 잘못되는 경우는 드묾) |
| coder | 3 | TLE→fix→다른에러 핑퐁 시 **3회면 부족할 수 있음** |
| auditor | 2 | 8개 미만 self-loop가 budget 소진할 수 있음 |
| generator | 2 | 충분 |

- 글로벌 `max_iter=5`와 노드별 합계 `9`의 관계: 글로벌이 먼저 트리거될 확률이 높아 per-node budget이 사실상 무의미해질 수 있음.

---

## 5. 문서별 상세 지표

| 지표 | PROJECT_SPEC | ARCHITECTURE | CHANGES |
|------|-------------|-------------|---------|
| 줄 수 | 434 | 1486 | 152 |
| 코드 블록 수 | 3 (Python, ASCII art, JSON) | ~30 | 2 (디렉토리 구조) |
| 테이블 수 | 8 | 12 | 3 |
| P0 항목 수 | 3 | 3 | 3 |
| P1 항목 수 | 8 | 8 | 8 |
| P2 항목 수 | 5 | 10 | 5 |
| 미해결 이슈 | 0 (CHANGES에 위임) | 0 | 4 |

---

## 6. 재기획을 위한 권장 조치

| # | 조치 | 우선순위 | 대상 파일 |
|---|------|---------|----------|
| 1 | ARCHITECTURE.md §6의 구 스키마를 삭제하고 SPEC §6을 SSOT로 지정 | 🔴 CRITICAL | ARCHITECTURE.md |
| 2 | ARCHITECTURE.md의 Evaluator 이중 코드를 통합 — Calibration anchor 포함 버전만 남기기 | 🔴 CRITICAL | ARCHITECTURE.md |
| 3 | macOS 개발 환경에 맞는 sandbox 정책 확정 — T1(Docker) 또는 T3(rlimit+경고) 중 선택 | 🟡 WARNING | PROJECT_SPEC.md |
| 4 | 교육 콘텐츠를 별도 파일로 분리 — CLI 에이전트의 컨텍스트 효율 향상 | 🟢 MINOR | ARCHITECTURE.md |
| 5 | 구현 시작 전 Q1~Q5에 대한 결정 선행 | 🔴 CRITICAL | — |
