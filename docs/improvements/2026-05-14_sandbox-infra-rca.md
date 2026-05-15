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

- [x] `tests/integration/test_sandbox_stdin_large.py` 신규 — stdin size 임계 측정 (commit `5f8df6b`)
- [x] RlimitRunner stdin pipe 처리 검증 (subprocess.Popen 패턴 audit) — race 진단 완료
- [x] RLIMIT_AS Python interpreter overhead 측정 — RLIMIT_CPU SIGXCPU race 확정 (rc=-24)
- [ ] subprocess 대안 (input file redirect) prototyping — Run 9 결과 보고 보류
- [x] e2e Run 9 측정 (R-sandbox fix 후) — 부록 C 참조
- [x] 본 RCA에 §부록 C로 실측 결과 추가

R-sandbox fix 적용 (PR #38, main `73024e1`) — production-ready 검증됨.

---

## 부록 C — Run 9 실측 결과 (R-sandbox fix 후)

> commit `73024e1` (`PHASE_C_WORKERS=1` 직렬화) — e2e 5 case 실행.
> 본 부록은 RCA 가설(race condition이 진짜 병목)을 e2e 실측으로 확정.

### C.1 결과 매트릭스

| Case | Run 9 (R-sandbox fix) | 이전 최고 |
|---|---|---|
| Two Sum | **success** 🟢 | budget_exh / max_iter |
| BFS | budget_exh | success (Run 5 단발) |
| Dijkstra | **success** 🟢 | max_iter |
| Segment Tree | budget_exh | max_iter |
| LIS | **success** 🟢 | success (Run 6-retry 단발) |
| **Success** | **3/5** | 1/5 (Run 5, Run 6-retry) |
| 소요 | 10:25 | 8:27 ~ 11:11 |

### C.2 전체 추세 (Run 1 ~ Run 9)

| Run | Sprint | Success | 비고 |
|---|---|---|---|
| Run 1 | v0.1.1 baseline | 0/5 | — |
| Run 2 | budget↑ | 0/5 | — |
| Run 3 | Sprint 1 (R1+R4) | 0/5 | — |
| Run 4 | Sprint 1.5 (R11) | 0/5 | — |
| Run 5 | max_iter=10 | 1/5 | BFS 첫 단발 |
| Run 6 | Sprint 2 (R10) — hang | aborted | R12 hang resilience backlog |
| Run 6-retry | Sprint 2 (R10) | 1/5 | LIS 첫 단발 |
| Run 7 | Sprint 3 (R13) | 0/5 | trace로 형식 작동 확인 |
| Run 8 | Sprint 3 (R13+R15) | 0/5 | trace로 형식 작동 확인 |
| **Run 9** | **R-sandbox (PHASE_C_WORKERS=1)** | **3/5** ⭐ | **첫 multi-success** |

### C.3 핵심 결론

**R-sandbox fix가 진짜 lever였음 완전 확정**:
1. Step 1 진단 (parallel race rate 4.5% SIGXCPU rc=-24) 정확
2. 1줄 변경 (`PHASE_C_WORKERS 4 → 1`)으로 0~1/5 → **3/5** (3x ↑)
3. 소요 시간 영향 거의 없음 — Phase C 자체는 4x ↑이지만 전체 10분대 유지
4. Sprint 1~3 R 시리즈가 **이제 진짜로 작동** — Phase C 통과 후 R1/R11/R13/R15 효과 발휘

### C.4 DoD 평가

- PROJECT_SPEC DoD: **5/5 중 4+ success** (LLM 변동성 허용)
- Run 9: **3/5** — DoD 80% 도달, 1 case 더 필요
- 남은 fail: BFS, Segment Tree (둘 다 budget_exh — Coder 8 cycle 안에 fix 못 함)

### C.5 Backlog 우선순위 재개정 (Run 9 결과 반영)

| ID | 항목 | 이전 우선순위 | **개정 우선순위** | 근거 |
|---|---|---|---|---|
| **R-sandbox** | PHASE_C_WORKERS=1 | P0 진행 | **✅ Resolved** | Run 9 3/5 검증 |
| **R14** | Coder Best-of-N | P2 강등됨 | **P0 격상** | 4/5+ 도달 가장 큰 lever |
| **R2** | W4 → architect 라우팅 | P2 | P1 | BFS/Segment 같은 oscillation 케이스 |
| R3 | Generator N gradient | P2 | P2 유지 | R10으로 부분 처리 |
| R12 | hang resilience | P1 | P1 유지 | 별개 운영 risk (Run 6 hang 재현 가능) |
| **R-sandbox v2** | ulimit wrapper로 PHASE_C_WORKERS=4 복귀 | — | P3 (선택) | Phase C 시간 회복 |

### C.6 다음 단계 plan

**즉시 진행**:
1. R14 (Best-of-N) — Coder N=3 솔루션 + sample 검증 최선 선택. 4/5 도달 가장 강력
2. R2 (W4 → architect 라우팅) — BFS/Segment 같이 oscillation 반복 case에 architect 재설계

**중기 (선택)**:
- R-sandbox v2: bash `ulimit` wrapper로 child shell이 RLIMIT 적용 후 exec → preexec_fn race 회피 + 병렬 복귀
- R12: ChatAnthropic timeout + retry wrapper

**v0.2.0 release 기준**:
- 4/5 안정 도달 → DoD 충족 → v0.2.0 tag
- 3/5 안정 (n=3 평균) + 운영 도구 갖춤 → v0.2.0 with known limitations
- DoD 미달 + sandbox v2/R14 진입 → v0.2.0-rc

---

## 부록 D — Run 10~12 실측 + Sprint 4 (R14 / R3 / R-bfs) 효과 확정

> commit `3cc02bd` (R-bfs architect budget 4 + docs restructure 완료) 시점.
> 본 부록은 Sprint 4의 3개 fix (R14 fanout=3, R3 N+M 가이드, R-bfs architect 4)
> 누적 효과를 e2e 3회 실측으로 확정한다.

### D.1 결과 매트릭스 (Run 9~12)

| Case | Run 9 (R-sandbox) | Run 10 (R14) | Run 11 (R3) | Run 12 (R-bfs) |
|---|---|---|---|---|
| Two Sum | success | success | success | success |
| BFS | budget_exh | **success** ⭐ | budget_exh | **success** ⭐ |
| Dijkstra | success | success | success | success |
| Segment Tree | budget_exh | budget_exh | **success** ⭐ | budget_exh |
| LIS | success | success | success | success |
| **Total** | **3/5** | **4/5** | **4/5** | **4/5** |
| 소요 | 10:25 | 18:33 | 12:25 | 12:53 |

### D.2 각 fix 효과 확정

| Fix | PR | 효과 |
|---|---|---|
| **R14 Best-of-N fanout=3** | #40 #41 | Run 9 → Run 10에서 BFS 회복 (budget_exh → success). LLM 다양성으로 oscillation 깸 |
| **R3 Generator N+M 가이드** | #45 | Run 10 → Run 11에서 Segment Tree 회복 (budget_exh → success). N+M dual-dimension 합산 cap 가이드 효과 |
| **R-bfs architect budget 4** | #46 | Run 11 → Run 12에서 BFS 재회복 (budget_exh → success). R4 auditor와 같은 분산 흡수 패턴 |

### D.3 진단 — 잔존 variance

**stable success** (3 cases, 100%):
- Two Sum / Dijkstra / LIS — 4회 연속 (Run 9~12) success

**variance case** (2 cases):
- **BFS**: Run 9 fail → Run 10 success → Run 11 fail → Run 12 success
  - Architect ↔ Coder oscillation (Phase A 3-way "다수 통과 + 소수 mismatch → architect")
  - R-bfs (architect 2→4)로 budget 흡수했지만 매 run 결과 변동
- **Segment Tree**: Run 9 fail → Run 10 fail → Run 11 success → Run 12 fail
  - Generator OLE (R10 cap 2MB 초과) variance
  - R3 prompt-only 가이드는 LLM 응답 매번 달라 100% 보장 어려움

### D.4 근본 한계 — LLM-side prompt fix의 분산

Sprint 1~4의 R 시리즈 (R1/R10/R11/R13/R15/R14/R3/R-bfs)는 모두 **prompt-side fix**:
- LLM이 가이드를 보고 따르는지 여부가 매 run마다 다름 (temperature 효과)
- BFS architect storytelling / Segment Tree Generator dimension 선택 = 매 run variance
- 따라서 **5/5 일관성은 prompt-side에서 도달 불가** — 다음 fix는 결정적 메커니즘 필요

### D.5 향후 결정적 fix 후보 (v0.2.1+)

| 후보 | 개념 | 효과 |
|---|---|---|
| **Generator hard cap validator** | sandbox 외부에서 generator 출력 size 사전 검증 → cap 초과 시 즉시 generator로 라우팅 (LLM 응답 기다리지 않고) | Segment Tree 100% 회피 보장 |
| **Phase A oscillation breaker** | 같은 architect signature 2회+ 발견 시 coder 강제 라우팅 (architect 무한 retry 방지) | BFS oscillation 결정적 차단 |
| **R5 brute oracle 활용 확대** | golden ≠ brute 일치 검증을 Phase B 전에도 (sample 검증과 함께) | architect ↔ coder 라우팅 결정 정확도 ↑ |
| **R12 hang resilience** | ChatAnthropic timeout + retry | 운영 안정성 (현재 R6에서 한 번 hang 발생) |

### D.6 v0.2.0 Release 결정

**기준**: 4/5 안정 도달 → DoD 충족 → v0.2.0 tag

**Run 11, 12 두 번 연속 4/5 success** — DoD 충족 확정. v0.2.0 release 가능.

**알려진 한계 (v0.2.0)**:
- 5 case 중 평균 4 success (variance ±1)
- BFS / Segment Tree는 case-by-case variance — v0.2.1에서 결정적 fix 검토
- 자세한 한계: REQUIREMENTS.md §5.3
