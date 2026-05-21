# R12 — Anthropic 일시 장애 retry/backoff (운영 안정성)

**Date**: 2026-05-18 (Round 14)
**Scope**: v0.2.1 결정적 fix sprint — Round 12 BFS Docker crash로 인한 P0 승격
**Related**: CHANGES.md §19, REQUIREMENTS.md §5.3,
`docs/improvements/2026-05-18_coder-osc-deterministic.md` (Round 12 측정)

---

## 1. 발견

### 1.1 Round 12 BFS Docker run crash

R-coder-osc 머지 후 BFS Docker run (`run_id: fe9ee7373222`)이 도중에 crash:

```
File "anthropic/_base_client.py", line 1147, in request
    raise self._make_status_error_from_response(err.response) from None
anthropic._exceptions.OverloadedError: Error code: 529 - {'type': 'error',
  'error': {'type': 'overloaded_error', 'message': 'Overloaded'},
  'request_id': 'req_011Cb9YV6mRjzm2LYepkHH7A'}
During task with name 'architect' and id '6f6db9a0-7bdd-a047-e03d-55e2d3478ef7'
```

**원인**: Anthropic 서버 일시 과부하 (HTTP 529 Overloaded). 즉시 raise → langchain → langgraph → 예외 전파 → 프로세스 crash.

**영향**:
- e2e 측정 도중 중단 → 결과 신뢰성 ↓ (재실행 비용 추가)
- 운영 시 동일 패턴 → 사용자 입장에서 "엔진이 가끔 죽는다"
- Round 13 sig-detail의 effective fix 검증을 BFS에서 못 함

### 1.2 langchain의 default 동작

`langchain_anthropic.ChatAnthropic`은 retry를 자동으로 제공하지 않음 (또는
default 0). `chat.invoke(messages)`가 예외 raise 시 호출자가 직접 처리.
IPE의 `LLMCallTracker.invoke`는 try/except 없음 → propagate.

---

## 2. 해법 — `_invoke_with_retry` + `_is_retryable`

### 2.1 HTTP status code 기반 분류

```python
_RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504, 529})

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        return isinstance(status, int) and status in _RETRYABLE_HTTP_STATUSES
    return False
```

| Status | 의미 | retry |
|---|---|---|
| 408 | Request Timeout | YES |
| 429 | Too Many Requests (RateLimit) | YES |
| 500 | Internal Server Error | YES |
| 502 | Bad Gateway | YES |
| 503 | Service Unavailable | YES |
| 504 | Gateway Timeout | YES |
| **529** | **Anthropic Overloaded** (vendor-specific) | **YES** ← Round 12 사례 |
| 400 | Bad Request (client error) | NO — raise |
| 401 / 403 | Auth / Permission | NO — raise |
| 404 | Not Found | NO — raise |

**Network 계열**: `APIConnectionError` (소켓 끊김), `APITimeoutError` (응답 없음) — isinstance fallback으로 retry.

### 2.2 Exponential backoff

```python
def _invoke_with_retry(chat, messages, *,
                       max_retries=3, base_backoff=2.0, sleep=time.sleep):
    last_exc = None
    for attempt in range(max_retries + 1):  # 4 attempts total
        try:
            resp = chat.invoke(messages)
            if not isinstance(resp, BaseMessage):
                raise TypeError(...)
            return resp
        except Exception as e:
            if not _is_retryable(e):
                raise  # 즉시 propagate
            last_exc = e
            if attempt == max_retries:
                break
            sleep(base_backoff * (2 ** attempt))  # 2, 4, 8 secs
    raise last_exc
```

**Backoff 시퀀스**:
- attempt 0 fail → sleep 2s
- attempt 1 fail → sleep 4s
- attempt 2 fail → sleep 8s
- attempt 3 fail → raise (총 4번 시도, 14초 대기)

**근거**:
- 14초 cap: Anthropic Overloaded는 보통 수십 초~수 분 단위로 회복. 14초 안에 회복 안 되면 raise하여 호출자 (run script)가 결정
- Jitter 미사용: 단일 사용자 단일 run이라 thundering herd 무관, 결정적 backoff가 디버깅에 유리
- max 3 retries: 더 많이 가도 cost 추가 + 회복 가능성 한계

### 2.3 design 선택지 vs 채택

| 옵션 | 채택? | 근거 |
|---|---|---|
| `anthropic._exceptions.OverloadedError` 직접 import | NO | private 모듈, SDK 변경 시 깨질 위험 |
| **HTTP status code 검사 (`APIStatusError.status_code`)** | **YES** | public surface, OverloadedError 포함 모든 5xx/4xx 처리 가능 |
| langchain의 `with_retry` runnable | NO | langchain-anthropic 버전 의존성 + 오버헤드 |
| tenacity 라이브러리 | NO | 새 dependency 도입 회피 (현 11 deps 유지) |

### 2.4 sleep injection

```python
def _invoke_with_retry(chat, messages, *,
                       sleep: Callable[[float], None] = time.sleep):
    ...
```

**테스트에서**: `sleep=sleeps.append` → 실제 대기 없이 호출만 기록. 14초 backoff 시나리오도 ms 단위로 검증 가능.

---

## 3. 통합 — `LLMCallTracker.invoke` 한 줄 변경

```python
# Before:
resp = chat.invoke(messages)

# After:
# R12 (Round 14): Anthropic 일시 장애 (529/429/timeout 등) 자동 retry.
resp = _invoke_with_retry(chat, messages)
```

기존 BaseMessage type check 중복 제거 (helper가 처리).

**Side effect**:
- `ReplayTracker.invoke`는 영향 없음 (chat.invoke 우회, cached response 직접 반환)
- 비용/메트릭/trace 저장은 retry 후 최종 success response 기준 (재시도 횟수 별도 기록 안 함 — 필요 시 향후 metric으로 추가 가능)

---

## 4. 테스트 (+13)

`tests/test_observability.py`:

| Class | Tests | 검증 |
|---|---|---|
| `TestIsRetryable` | 6 | RateLimit / Overloaded(529) / 5xx / 408 / 4xx 제외 / 일반 예외 제외 |
| `TestInvokeWithRetry` | 6 | 첫 success / 1 retry / 2 retry exp backoff / max exhausted raise / 비-retryable 즉시 raise / 일반 예외 즉시 raise |
| `TestLLMCallTrackerUsesRetry` | 1 | tracker.invoke가 retry 사용 — Overloaded 1회 후 자동 복구 (Round 12 시나리오 재현) |

핵심 테스트: `test_all_retries_exhausted_raises_last` — 4번 모두 실패 시
정확히 4번 호출 + 3번 backoff (2/4/8s) + 마지막 예외 propagate.

전체 회귀: **314 passed + 3 skipped** (Round 13의 301 + 본 PR +13).

---

## 5. 한계 + 후속

- **14초 cap**: 길게 hang하는 Anthropic 장애 (수 분급)는 여전히 raise. CLI에서
  더 긴 retry 원하면 `_R12_MAX_RETRIES` / `_R12_BASE_BACKOFF_SECS` 조정 가능.
- **retry 메트릭 미수집**: 몇 번 retry 후 success했는지 별도 metric으로 기록 안 함.
  운영 모니터링 필요 시 `emit_metric("ipe.node.retry_count", ...)` 추가 가능.
- **Jitter 없음**: 단일 사용자 단일 run이라 thundering herd 무관. 다중 사용자
  배치 시 jitter 도입 권장 (`random.uniform(0.5, 1.5)`).
- **Phase C parallel call에는 영향 0**: Phase C는 sandbox subprocess 호출 (LLM 아님).
- **e2e 재실측 권장**: R-sig-detail (Round 13) + R12 (Round 14) 둘 다 적용 후
  BFS + SegTree Docker 재실측 → oscillation 루프 해소 + 529 자동 복구 검증.
  → v0.2.1 release 검증.
