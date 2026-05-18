# R-docker-workdir — DockerRunner cwd 절대경로 fix (인프라)

**Date**: 2026-05-18 (Round 15)
**Scope**: v0.2.1 release 진입 전 발견된 Docker 인프라 버그
**Related**: CHANGES.md §20, REQUIREMENTS.md §5.3,
`docs/improvements/2026-05-18_sig-detail.md` (Round 13 — 본 버그가 드러난 계기)

---

## 1. 발견 — Round 14 e2e 재실측 결과

### 1.1 BFS + SegTree Docker 둘 다 budget_exhausted

Round 13 R-sig-detail + Round 14 R12 머지 후 e2e Docker 재실측:

```
BFS run_id: fa491a961832, final: budget_exhausted, iter 6
SegTree run_id: 81d2f297289c, final: budget_exhausted, iter 6
```

R-sig-detail 덕분에 feedback에 stderr 노출:

```
iter 1 coder retry sig=da822803 fb=phase A failures: 5/5 [
    idx=0:RTE stderr="docker: Error response from daemon: the working
    directory 'workdir/run_xxx' is invalid, it needs to be an absolute
    path" | idx=1:RTE stderr="docker:..." | ...]
```

**모든 sample이 RTE — solution이 실행도 안 됨**. Docker daemon이 sandbox call 자체를 거부.

### 1.2 원인 — main.py의 상대경로 + DockerRunner의 무처리

`main.py:35`:
```python
WORKDIR_ROOT = Path("workdir")  # ← 상대경로
```

`DockerRunner.run`이 받은 `spec.cwd`를 그대로 `--workdir`와 `--tmpfs`에 전달:
```python
f"--tmpfs={spec.cwd}:rw,...",
f"--workdir={spec.cwd}",
```

Docker는 `--workdir` 인자에 절대경로를 요구. `workdir/run_xxx` 같은 상대경로 → daemon 거부.

### 1.3 왜 prior Round 12 측정에서 안 드러났는가

Round 12 SegTree 측정에서도 같은 인프라 버그가 있었을 가능성이 높지만:
- R-sig-detail 없이는 feedback이 `"phase A failures: 4/4"`로 generic
- coder oscillation처럼 보였음 — **misdiagnosis**
- Round 13 R-sig-detail가 stderr를 feedback에 노출시키면서 비로소 정확한 진단 가능

이는 **observability 개선이 진짜 fix의 시작점**이라는 메타-교훈.

---

## 2. 왜 이전엔 안 터졌는가 (탐색 가설)

| 시나리오 | Docker workdir 절대경로? |
|---|---|
| `pytest tests/e2e/test_smoke.py` | `tmp_path` (pytest fixture, 절대경로) → OK |
| `python main.py --sandbox rlimit` | RlimitRunner는 OS chdir로 상대경로 처리 → OK |
| `python main.py --sandbox docker` | **상대 `workdir/run_xxx` → Docker 거부 → fail** |

즉 본 fix 전엔 e2e 테스트(pytest fixture)와 RlimitRunner 경로는 OK였고, **CLI + Docker 조합만** fail이었다. v0.2.0 e2e DoD가 4/5인 것은 pytest 경로로 측정해서 영향 없었음.

main.py + Docker 조합은 R-osc-break 검증 시점에 처음 시도된 듯하며, 그때부터 잠재해 있던 버그가 Round 13 R-sig-detail 후 비로소 노출.

---

## 3. 해법 — 이중 안전망

### 3.1 `DockerRunner.run()` 자체 방어 (1차)

```python
def run(self, spec: RunSpec) -> RunResult:
    # R-docker-workdir: Docker는 --workdir/--tmpfs에 절대경로 필수.
    cwd_abs = str(Path(spec.cwd).resolve())
    cmd = [
        "docker", "run", "--rm",
        "--network=none",
        "--read-only",
        f"--tmpfs={cwd_abs}:rw,size={spec.memory_limit_mb}m,exec",
        ...
        f"--workdir={cwd_abs}",
        ...
    ]
```

DockerRunner 진입점에서 자동 절대화 → 모든 호출자에게 보호.

### 3.2 `main.py` 호출자 측 안전망 (2차)

```python
OUTPUTS_ROOT = Path("outputs").resolve()
WORKDIR_ROOT = Path("workdir").resolve()
```

DockerRunner fix만으로 충분하지만, main.py에서도 명시적으로 절대화 → 향후
다른 호출자가 같은 실수 안 하도록 신호.

### 3.3 idempotent — 이미 절대경로면 변경 없음 (sort of)

`Path("/tmp/x").resolve()`는 symlink 해석 (macOS `/tmp` → `/private/tmp`).
의미적으로 동일한 절대경로지만 문자열은 다를 수 있음. Docker 동작에는 영향 없음.

---

## 4. 테스트 (+7)

`tests/sandbox/test_docker_workdir.py` (신규, mock subprocess 기반 — Docker daemon 없이 결정적):

| Test | 검증 |
|---|---|
| `test_relative_cwd_resolved_to_absolute_in_workdir` | 상대 `workdir/run_test` → `--workdir`가 절대경로 |
| `test_relative_cwd_resolved_in_tmpfs` | 상대 `rel/path` → `--tmpfs` path도 절대 |
| `test_absolute_cwd_stays_absolute` | `/tmp/already_abs` → 절대 유지 (symlink 해석 허용) |
| `test_dotted_relative_cwd_resolved` | `./local` → 절대화 |
| `test_workdir_and_tmpfs_match[...]` × 3 | `--workdir`와 `--tmpfs` path 일치 (parametrize) |

핵심: subprocess.run을 patch하여 cmd 인자를 capture, `--workdir=` prefix 검사.

전체 회귀: **321 passed + 3 skipped** (Round 14의 314 + 본 PR +7).

---

## 5. 메타-교훈

### 5.1 observability가 진짜 fix의 시작점

Round 11~14의 결정적 fix를 차례로 적용했지만:
- Round 12 측정에서 본 "coder oscillation 4/4 반복" → 실제로는 인프라 버그였음
- R-sig-detail (Round 13)이 stderr를 feedback에 노출시키면서 비로소 진단 가능
- 즉, **잘 정의된 fix들이 무의미해 보이는 패턴을 만들었을 때, 더 fix를 쌓기 전에 observability를 의심해야 함**

### 5.2 sandbox tier 간 의미차

| Runner | 상대 cwd | 절대 cwd |
|---|---|---|
| RlimitRunner (T3) | OS `chdir`로 처리 — OK | OK |
| SandboxExecRunner (T2.5) | sandbox profile에 의존 — 일반적으로 OK | OK |
| **DockerRunner (T1)** | **거부** | OK |

Tier 추상화의 invariant 위반. 본 fix로 invariant 회복.

### 5.3 후속 안전망

- DockerRunner의 isolation_self_test에 상대경로 케이스 추가 가능 (Phase 2)
- `RunSpec`의 cwd 필드에 `Path` 타입 + `@validator` 강제 — 더 깊은 fix지만 큰 변경

---

## 6. 한계 + 후속

- **DockerRunner.isolation_self_test()는 상대경로 케이스 미포함**: 본 PR은 cmd 생성 단위로 검증. 실제 docker daemon 통합 self-test는 별도 (`@pytest.mark.slow`).
- **e2e 재실측 필요**: 본 fix 후 BFS + SegTree Docker 재실측 → Round 11~13 결정적 fix의 진짜 효과 측정 → v0.2.1 release.
- **OUTPUTS_ROOT 절대화의 side effect**: `outputs/<run_id>/`가 cwd 기준 절대 경로로 저장. 기존 상대경로 가정한 코드 있는지 확인 (검색 결과 없음).
