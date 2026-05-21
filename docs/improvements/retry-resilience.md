# Retry Resilience — Anthropic API 일시 장애 대응

**Last updated**: 2026-05-21
**Scope**: Anthropic API 의 529 (Overloaded) / 429 (Rate Limit) / timeout 등
일시 장애에 자동 retry + backoff.
**Status**: 운영 중. v0.3.0 N=3 측정에서 일부 long 단절 (1시간 Anthropic-side
overload) 도 회복 데이터 확보.

원본 RCA: [`2026-05-18_r12-retry-resilience.md`](../archive/improvements/2026-05-18_r12-retry-resilience.md)

---

## 0. 개요

LLM 호출의 HTTP error 가 일시적일 경우 (Anthropic 측 throttling / overload)
naive raise 는 IPE run 전체 중단. R12 는 retryable HTTP status 판별 + exponential
backoff 도입.

---

## 1. 포함된 fix

| Round | Fix | 원본 RCA | 영향 |
|---|---|---|---|
| 14 | R12 retry/backoff | [`2026-05-18_r12-retry-resilience.md`](../archive/improvements/2026-05-18_r12-retry-resilience.md) | 529/429/timeout 자동 retry |

---

## 2. 설계

### 2.1 retryable status

| HTTP | retryable | 처리 |
|---|---|---|
| 529 (Overloaded) | ✓ | retry |
| 429 (Rate Limit) | ✓ | retry |
| 502/503/504 | ✓ | retry |
| timeout (connect/read) | ✓ | retry |
| 4xx (client error 외 429) | ✗ | 즉시 raise (invalid request / auth fail) |

### 2.2 backoff schedule

- attempt 1: 2초 대기
- attempt 2: 4초 대기
- attempt 3: 8초 대기
- max retries: 3
- total wait cap: ~24초

### 2.3 적용 위치

`ipe/observability.py:_invoke_with_retry` — 모든 LLM call (architect / designer
/ coder / reviewer / auditor / generator / evaluator / baseline) 이 동일하게
보호.

---

## 3. 측정 데이터 (v0.3.0 N=3 measurement)

- IPE r3 측정 중 Anthropic 529 발생 → 24초 retry exhausted → 모든 6 runs 가
  ~49s 에 fail
- 사용자 인터럽트 + Anthropic 회복 대기 (~1시간) → 재실행 시 정상 동작
- R12 의 24초 cap 은 짧은 단절 (< 24초) 만 cover. 장기 단절 (분/시간 단위) 은
  user-level retry 필요

---

## 4. Rollback trigger (PRINCIPLES.md 룰 5)

- 운영 fix 라 rollback 보다는 "회복 조건" 형식:
  - Anthropic 529 가 N=3 measurement 동안 발생 → R12 가 그 cap (24초) 내 회복
    하면 OK
  - 발생 빈도 ≥ 5% / measurement → R12 cap 확대 검토 (8초 → 30초, max retries
    3 → 5)

---

## 5. 후속 개선 후보

- **장기 단절 대응**: 24초 cap 초과 시 graceful pause → user-level resume
  (`ipe --resume <run_id>` 활용). 현재는 user 가 수동 stop 후 재실행 필요.
- Anthropic status page polling 통합 (전역 outage 자동 감지).
- 모델별 retry policy 분리 (Opus 가 Sonnet 보다 throttle 빈도 ↑ 면 모델별 cap
  다르게).
