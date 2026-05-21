# R-docker-mount — DockerRunner bind mount fix (deeper 인프라)

**Date**: 2026-05-18 (Round 16)
**Scope**: v0.2.1 release 전 발견된 2차 Docker 인프라 버그 (Round 15 fix 후 노출)
**Related**: CHANGES.md §21,
`docs/improvements/2026-05-18_docker-workdir-fix.md` (Round 15 — 1차 인프라 fix)

---

## 1. 발견 (Round 15 재실측)

R-docker-workdir 머지 후 BFS + SegTree Docker 재실측 결과:

```
BFS run_id b040d9387037: final=budget_exhausted, iter=6
SegTree run_id 5a66a428294a: final=budget_exhausted, iter=7
모두 RTE — "python3: can't open file '/Users/iseungmin/claude_ws/IPE/wor..."
```

workdir 절대경로는 정상 (Round 15 fix 확인) 그러나 **컨테이너 안에서 solution.py 못 찾음**.

---

## 2. 진짜 원인 — `--tmpfs`의 mask 효과

기존 `DockerRunner.run`:

```python
"--tmpfs", f"{cwd_abs}:rw,size={spec.memory_limit_mb}m,exec"
```

**`--tmpfs={path}`는 그 path 위에 빈 tmpfs를 오버레이 마운트**. 호스트의 파일은
마스킹되어 컨테이너에서 안 보임.

```
호스트:       /Users/.../workdir/run_xxx/solution.py  (있음, executor가 작성)
컨테이너 안:  /Users/.../workdir/run_xxx/               (빈 tmpfs, 호스트 내용 mask됨)
```

컨테이너에서 `python3 solution.py` → 빈 tmpfs에서 못 찾음 → RTE.

### 2.1 왜 isolation_self_test는 통과했나

```python
# DockerRunner.isolation_self_test():
cwd = "/work"  # Dockerfile WORKDIR
cmd = ["python3", "-c", script]  # inline code
```

파일 의존 없는 **inline code** 실행이라 tmpfs가 비어도 OK.

**함정**: sanity check가 실제 사용 패턴 (`python3 solution.py`)을 cover 못 함.
"isolation works"라는 거짓 안심을 줌.

### 2.2 왜 RlimitRunner는 OK였나

RlimitRunner는 호스트 위에서 직접 subprocess 실행. 호스트 fs 그대로 보임 →
`solution.py` 보임. BFS RlimitRunner success (Round 11) vs Docker 모든 sample
fail (Round 14~15) 차이의 진짜 원인.

**SandboxedRunner tier 추상화의 invariant 위반**: 모든 tier가 "주어진 cwd에서
spec.cmd 실행"이라는 동일 의미를 보장해야 하지만 Docker는 cwd 내용이 사라지는
특수 동작.

---

## 3. 해법 — bind mount

```python
# Before (Round 15 stop):
"--tmpfs", f"{cwd_abs}:rw,size={spec.memory_limit_mb}m,exec"

# After (Round 16):
"-v", f"{cwd_abs}:{cwd_abs}:rw"
```

| 측면 | 변화 |
|---|---|
| 호스트 cwd → 컨테이너 cwd | **bind mount** — 같은 절대경로 readwrite |
| 호스트 파일 가시성 | 컨테이너 안에서 보임 |
| `--read-only` rootfs | **유지** — cwd 외에는 못 씀 (격리 보존) |
| 메모리 격리 | `--memory={N}m` 유지 |
| network 격리 | `--network=none` 유지 |
| fork 격리 | `--pids-limit` 유지 |
| CPU 격리 | `--cpus=1` 유지 |

격리 보장은 동일하면서 file visibility 회복.

### 3.1 macOS Docker Desktop 고려

macOS는 Docker가 VM 안에서 실행. bind mount는 VM의 file sharing 설정에 의존.
default sharing path: `/Users/`, `/Volumes/`, `/private`, `/tmp` 등.

본 프로젝트의 workdir은 `/Users/iseungmin/claude_ws/IPE/workdir/...` →
default `/Users/` sharing에 포함 → OK. 다른 path에 workdir 두면 user가
Docker Desktop 설정에 path 추가 필요 (사용자 환경 의존, code 수정 불필요).

### 3.2 sanity check (real Docker)

```python
with tempfile.TemporaryDirectory(dir='/tmp') as td:
    Path(td, 'hello.py').write_text('print("hi from host file")')
    res = DockerRunner().run(RunSpec(cmd=['python3', 'hello.py'], cwd=td))
    # status: OK, stdout: 'hi from host file\n'
```

실측으로 fix 검증 완료.

---

## 4. 운영 영향 + 테스트 영향

### 4.1 운영

Phase A `_execute_solution(runner, run_dir, ...)`, Phase C `_run_generator(runner, gen_dir, ...)` 모두 sandbox 호출 전에 `run_dir.mkdir()` / `gen_dir.mkdir()` 수행. bind mount source 항상 존재 → 영향 0 (운영 코드 수정 불필요).

### 4.2 기존 isolation 테스트

`tests/sandbox/test_isolation.py::TestDockerRunner`는 `cwd="/work"` 사용. 이전엔 tmpfs라 host에 없어도 OK였지만 bind mount는 host path 존재 필수 → 2 test fail. `tmp_path` fixture로 수정 (pytest가 절대경로 자동 제공).

### 4.3 회귀 방지 mock 테스트

`tests/sandbox/test_docker_workdir.py`:
- `--tmpfs` 검증 (3 test) → `-v` 검증으로 갱신
- `test_no_tmpfs_overlay` 신규 — `--tmpfs`가 cmd에 없음을 명시 (회귀 방지)
- `test_workdir_and_bind_match` — `--workdir`와 `-v` container path 일치

---

## 5. 테스트 (+1 신규, 3 갱신)

| Test | 변화 |
|---|---|
| `test_relative_cwd_resolved_in_bind_mount` | `--tmpfs` → `-v` 검증 (rename + body) |
| `test_no_tmpfs_overlay` | **신규** — `--tmpfs` 없음 (회귀 방지) |
| `test_workdir_and_bind_match[...]` × 3 | `--workdir`와 `-v` container path 일치 (rename + body) |
| `test_basic_echo` (isolation, slow) | `cwd="/work"` → `tmp_path` |
| `test_network_blocked` (isolation, slow) | `cwd="/work"` → `tmp_path` |

전체 회귀: **322 passed + 3 skipped** (Round 15의 321 + 신규 1).

---

## 6. 메타-교훈

### 6.1 인프라 버그는 layer 단위로 드러남

| Round | 발견 |
|---|---|
| 13 R-sig-detail | observability 개선 → 인프라 버그 1 (workdir 상대경로) 노출 |
| 15 R-docker-workdir | 인프라 버그 1 fix → **인프라 버그 2 (tmpfs mask) 노출** |
| **16 R-docker-mount** | **인프라 버그 2 fix → 진짜 e2e 측정 가능** |

첫 fix 후 즉시 재실측의 가치. "고치고 다음 measurement까지 미루면" 누적된
issue가 한 번에 안 드러나서 misdiagnosis 위험 ↑.

### 6.2 sanity check의 함정

isolation_self_test는 inline code (`python3 -c`)로만 검증해서 실제 사용 패턴
(`python3 file.py`)에서 발생하는 버그를 못 잡았다.

후속 개선: isolation_self_test에 "host file 보이는지" probe 추가 — 본 PR
scope 밖이지만 v0.2.2 candidate로 backlog 등록.

### 6.3 tier 추상화의 invariant

모든 `SandboxedRunner.run(spec)`는 "주어진 spec.cwd에서 spec.cmd 실행"이라는
의미를 보장해야 함. RlimitRunner/SandboxExecRunner는 호스트 fs 그대로 사용 →
자연스럽게 invariant 만족. DockerRunner는 격리 추가하면서 invariant 위반 →
본 PR로 회복.

---

## 7. 한계 + 후속

- **macOS Docker Desktop file sharing path 의존**: workdir이 default sharing path 밖에 있으면 user가 Docker Desktop 설정 추가 필요. 운영 default (`workdir/run_xxx/` under cwd)는 일반적으로 OK.
- **isolation_self_test에 file-based probe 추가**: 본 PR scope 밖. v0.2.2 candidate.
- **bind mount의 보안 의미**: 호스트의 cwd가 컨테이너에서 r/w. cwd 자체가 untrusted code가 쓸 수 있는 영역 (Phase B/C 의도된 동작). cwd 외에는 `--read-only` rootfs로 보호됨. 호스트 다른 영역 보호 유지.
- **e2e 재실측 필요**: 본 fix 후 BFS + SegTree Docker 재실측 → Round 11~13 결정적 fix의 진짜 효과 측정 → v0.2.1 release.
