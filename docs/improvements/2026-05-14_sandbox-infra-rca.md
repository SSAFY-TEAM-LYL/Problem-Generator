# Sandbox Infra RCA — Sprint 3 실행 후 진짜 병목 확정

> Sprint 3 (R13 Reflexion + R15 Brute oracle cross-check) 적용 후 e2e Run 7/8
> 측정 결과 0/5 success. 그러나 **trace 분석 + 로컬 reproduction**에서
> Sprint 1~3 R 시리즈가 형식상 정상 작동했음에도 success 도달 못 한 진짜
> 원인이 **sandbox runner infra**임을 확정.
>
> 본 문서는:
> 1. Sprint 3 실행 결과 (Run 7/8)
> 2. Trace 분석 — R13/R15 형식 작동 확인
> 3. 로컬 reproduction — 솔루션은 sandbox 밖에서 정상
> 4. 진단 — RlimitRunner stdin/RLIMIT 가설
> 5. 다음 단계 A — sandbox infra 디버깅 plan
> 6. troubleshooting flow update — sandbox-aware diagnosis
>
> **참조**: [RCA v0.1.1](2026-05-10_root-cause-analysis.md) ·
> [Troubleshooting Playbook](2026-05-14_quality-troubleshooting.md)

---

## Executive Summary

### 핵심 결론
1. **Sprint 1~3 R 시리즈 (R1/R4/R6/R10/R11/R13/R15)는 형식상 모두 정상 작동** — trace로 검증됨
2. **그러나 e2e success rate는 0~1/5 정체** — R 시리즈가 본질 fix 아니었음
3. **진짜 병목은 sandbox runner infra** — Phase C stress에서 솔루션이 22ms RTE
4. **로컬에서 동일 솔루션 + 동일 입력 정상 작동** (40ms exit 0)
5. **결론**: LLM-side 추가 R 시리즈 (R14 Best-of-N 등)보다 **sandbox infra 진단이 ROI 최대**

### Sprint 3 실측 매트릭스

| Case | Run 6-retry (R10) | Run 7 (R13) | Run 8 (R13+R15) |
|---|---|---|---|
| Two Sum | budget_exh | budget_exh | budget_exh |
| BFS | budget_exh | budget_exh | budget_exh |
| Dijkstra | max_iter | budget_exh | budget_exh |
| Segment Tree | budget_exh | budget_exh | budget_exh |
| LIS | **success** | budget_exh | budget_exh |
| **Success** | **1/5** | **0/5** | **0/5** |
| 소요 | 9:41 | 8:58 | 11:11 |

---

## 1. Sprint 3 R 시리즈 형식 작동 검증

### 1.1 R13 (Reflexion) — Coder LESSON 추출 누적

Run 8 Two Sum trace `0008_coder.json` 검사:

```
LESSON: Previous attempts kept getting RTE on large inputs despite claiming
to use buffered IO — need to ensure the solution is truly minimal and uses
sys.stdin.buffer.read().split() correctly with no extraneous overhead.
```

- ✅ LESSON 형식 준수
- ✅ 구체적 (이전 fail 원인 + 새 strategy 명시)
- ✅ history에 누적되어 다음 cycle prompt에 노출

### 1.2 R15 (Brute Oracle) — golden + brute 두 fence

같은 trace의 response 내용:
- 첫 펜스 (가장 긴): O(N log N) hash+bisect golden solution
- 두 번째 펜스: O(N²) double-loop brute solution
- ✅ 두 fence 정상 출력 — `_parse_response`가 정확히 추출

### 1.3 R1 (detailed feedback) + R11 (HIGH-VOLUME warning)

Coder가 받은 prompt user message:

```
phase C: solution failed on 2 stress cases (RTE/TLE/MLE)

⚠️  HIGH-VOLUME INPUT detected (max 2.08 MB). Default line-by-line IO will
TLE/RTE — switch to buffered IO:
  - Python: `data = sys.stdin.buffer.read().split()`
  - Java:   BufferedReader + StreamTokenizer
  - Output: collect into list, then sys.stdout.write

Failing cases (first 2):
  1. phase=stress status=RTE elapsed_ms=26 generator=gen_max_stress seed=1
     input_bytes=878566
     input: '200000 1629\n-725 165 735 643 564 -871 -478 -759 14 558 ...'
  2. phase=stress status=RTE elapsed_ms=30 generator=gen_max_stress_no_pair
     seed=2 input_bytes=2077262
     input: '200000 718471049\n853513164 ...'
```

- ✅ R1 detailed feedback (status / elapsed_ms / generator / seed / input_bytes / input excerpt)
- ✅ R11 HIGH-VOLUME warning 발화 (max 2.08 MB)
- ✅ W4 oscillation history 누적

**즉 모든 R 시리즈 prompt-side 시그널이 정상 도달**. Coder가 보지 못해서 fix 안 한 게 아님.

---

## 2. 결정적 발견 — 로컬 Reproduction은 정상

Two Sum의 마지막 cycle Coder 솔루션은 production-grade O(N log N):

```python
import sys
from collections import defaultdict
import bisect

def main():
    data = sys.stdin.buffer.read().split()  # buffered IO ✅
    n = int(data[0])
    T = int(data[1])
    f = [int(data[i + 2]) for i in range(n)]

    val_to_indices = defaultdict(list)
    for i in range(n):
        val_to_indices[f[i]].append(i)

    best_i = -1
    best_j = -1
    for i in range(n):
        need = T - f[i]
        if need in val_to_indices:
            indices = val_to_indices[need]
            pos = bisect.bisect_right(indices, i)
            if pos < len(indices):
                # ... (binary search for smallest j > i)
```

### 2.1 로컬 실행 결과 (3 seed × N=200000)

| seed | input size | real time | exit | stderr |
|---|---|---|---|---|
| 1 | 878,566 bytes | 0.04s | **0** | (empty) |
| 2 | 878,131 bytes | 0.04s | **0** | (empty) |
| 3 | 878,603 bytes | 0.04s | **0** | (empty) |

- ✅ 모든 seed 40ms 안에 정상 종료
- ✅ stderr 비어있음 (RTE/exception 없음)
- ✅ stdout 정상 답 출력 (`3 499` 등)

### 2.2 e2e sandbox 실행 결과

| seed | input size | elapsed_ms | status |
|---|---|---|---|
| 1 | 878,566 bytes | **22** | **RTE** |
| 2 | 2,077,262 bytes | 30 | RTE |

- 🔴 22ms는 Python interpreter 시작 시간보다 짧음 (보통 50ms+)
- 🔴 process가 솔루션 코드 실행 도달 전 abort
- 🔴 stderr 정보가 prompt에 안 노출됨 (sandbox stderr 캡처 부재 또는 비어있음)

---

## 3. 진단 — RlimitRunner Sandbox Infra 가설

### 3.1 가능한 원인 (순위)

| 가설 | 가능성 | 근거 |
|---|---|---|
| **stdin pipe SIGPIPE / 부분 write** | 🟢 가장 높음 | 22ms는 process 시작 단계, large stdin write fail 시점과 일치 |
| **RLIMIT_AS Python interpreter OOM** | 🟡 중간 | 512MB Python+dict+list 정상 처리해야 하나 일부 환경 OOM |
| **RLIMIT_NPROC / RLIMIT_STACK** | 🟡 중간 | Python multiprocessing/threading 영향 가능 |
| **Sandboxexec policy 거부** (macOS) | 🟡 중간 | macOS sandbox-exec 정책이 large stdin 거부 |
| **subprocess.Popen stdin buffer 한도** | 🟢 높음 | Python default stdin pipe buffer 64KB — 875KB 쓰면 deadlock 가능 |

### 3.2 가장 유력 — Subprocess stdin pipe deadlock

```python
# RlimitRunner pattern (simplified)
proc = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE,
                        preexec_fn=_build_preexec(spec))
stdout, stderr = proc.communicate(input=stdin_text, timeout=...)
```

`communicate(input=...)`는 통상적으로 안전하지만:
- stdin이 매우 클 때 child process가 stdin 다 읽기 전에 다른 syscall(예: fork)을 시도하면 RLIMIT_AS 한도 초과로 즉시 RTE
- 또는 communicate 내부 timeout이 stdin write 완료 전에 발화

### 3.3 검증 plan (다음 PR)

1. **Sandbox isolation reproduction**:
   - `RlimitRunner.run()`을 직접 호출 (e2e 없이) — 같은 stdin/solution 조합
   - 정확히 어느 단계에서 fail하는지 stderr 캡처 강화
2. **stdin size 조절**:
   - 100KB, 500KB, 875KB, 2MB 점진 증가 — 임계값 찾기
3. **RLIMIT 변수**:
   - RLIMIT_AS 비활성화 후 재현
   - RLIMIT_AS만 4GB로 키운 케이스
4. **subprocess 대안**:
   - `Popen.stdin.write` 명시적 split write
   - 또는 stdin을 임시 파일로 분리 (`< input.txt` redirect)

---

## 4. 향후 troubleshooting flow update (sandbox-aware)

### 4.1 e2e 0/5 결과 → 진단 (개정)

```
1. trace 분석 → R1/R11/R13/R15 형식 작동 확인
   ↓
2. Coder LLM 응답 자체 분석 (head 500 chars) — algorithm 적절성 검증
   ├─ 부정확한 algorithm → R14 (Best-of-N) 또는 R13 lesson 강화
   └─ 정확한 algorithm but stress fail → 3 진입
   ↓
3. 로컬 reproduction (이 RCA의 §2 패턴):
   - solution.py + generators/<name>.py를 /tmp/repro_<ts>/에 복사
   - 직접 ``python3 generator.py <seed> | python3 solution.py`` 실행
   ├─ 로컬 fail → 진짜 algorithm 문제 → LLM-side fix
   └─ 로컬 OK + e2e fail → **sandbox infra 문제 확정** (4 진입)
   ↓
4. Sandbox infra 진단:
   - RlimitRunner direct invocation
   - stdin size 점진 증가
   - RLIMIT 변수 실험
   - subprocess 대안 (stdin 파일 redirect)
```

### 4.2 hang 진단 (기존 R12와 통합)

본 sandbox infra 진단과 hang 진단은 같은 backlog 그룹 — RlimitRunner 신뢰성 개선.

---

## 5. v0.2.0 Sprint 3+ Backlog 우선순위 (개정)

| ID | 항목 | 이전 우선순위 | **개정 우선순위** | 근거 |
|---|---|---|---|---|
| **R-sandbox** (신규) | RlimitRunner stdin/RLIMIT 디버깅 + fix | — | **🔴 P0** | 진짜 병목 확정 |
| R12 | hang resilience (ChatAnthropic timeout) | P1 | P1 (변동 X) | 별개 운영 risk |
| R14 | Coder Best-of-N | P1 | P2 강등 | R-sandbox 통과 후에야 의미 |
| R2 | W4 → architect 라우팅 | P1 | P2 강등 | Phase C 도달 후 효과 |
| R3 | Generator N gradient | P1 | P2 강등 | R10 + R11로 부분 처리 |

---

## 6. 진행 plan (A 본격)

### 6.1 Step 1 — Reproduction PR
- `tests/integration/test_sandbox_stdin_large.py` 신규 — 100KB/500KB/875KB/2MB stdin을 RlimitRunner로 직접 실행
- 어느 size부터 RTE인지 확정
- macOS/Linux 환경 차이 측정

### 6.2 Step 2 — RLIMIT 디버깅 PR (Step 1 결과 기반)
- 가설 A (stdin pipe): `subprocess.Popen` 사용 패턴 검토 + 대안 (input file redirect)
- 가설 B (RLIMIT_AS): Python 기본 + 사용자 코드 합산 RLIMIT 계산
- 가설 C (preexec_fn race): preexec_fn 안에서 별도 syscall 영향 검증
- 진단 결과에 따라 fix 적용

### 6.3 Step 3 — e2e Run 9 재측정
- R-sandbox fix 후 동일 5 case 측정
- success rate baseline 회복 + 잠재적 ↑

### 6.4 후속 (선택)
- Step 1-3 결과 검토 후 R14 / R2 / R3 진입 여부 결정
- DoD 4/5 달성 시 v0.2.0 release tag
- 5/5 못 달성 시 DoD 완화 정책 (1+/5 또는 평균 2/5) 명시

---

## 부록 A — Sprint 1~3 효과 솔직한 재평가

| R | 의도 | 작동 여부 | 실효 |
|---|---|---|---|
| R1 | detailed feedback | ✅ trace 확인 | ❓ Phase C 도달 후만 — 현재 미달 |
| R4 | auditor budget 4 | ✅ Two Sum Run 2→3 변동 흡수 | ✅ 부분 효과 |
| R6 | PRICING 주석 | ✅ 문서화 | ✅ 운영 평가 정확성 ↑ |
| R10 | Generator size cap 2MB | ✅ truncated 시 routing | ✅ 부분 효과 (Run 6-retry LIS success 기여 가능) |
| R11 | HIGH-VOLUME warning | ✅ trace 확인 (max 2.08MB 발화) | ❓ Coder가 본 후에도 sandbox에서 RTE |
| R13 | LESSON 누적 | ✅ trace 확인 (구체 reflection) | ❓ Phase C 도달 못 하면 의미 0 |
| R15 | brute cross-check | ✅ 두 fence 추출 | ❓ Phase C 통과 후 트리거 — 미도달 |

**핵심**: R 시리즈는 모두 **LLM-side 입력 quality 개선**. Sandbox 측 실행이 실패하면 어떤 LLM-side 개선도 의미 없음.

---

## 부록 B — 다음 PR 체크리스트

본 RCA 머지 후:

- [ ] `tests/integration/test_sandbox_stdin_large.py` 신규 — stdin size 임계 측정
- [ ] RlimitRunner stdin pipe 처리 검증 (subprocess.Popen 패턴 audit)
- [ ] RLIMIT_AS Python interpreter overhead 측정
- [ ] subprocess 대안 (input file redirect) prototyping
- [ ] e2e Run 9 측정 (R-sandbox fix 후)
- [ ] 본 RCA에 §부록 C로 실측 결과 추가

R-sandbox fix가 production-ready 되면:
- R14/R2/R3 진입 여부 재검토
- v0.2.0 release 또는 DoD 완화 정책 결정
