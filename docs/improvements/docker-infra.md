# Docker Sandbox Infra — workdir + bind mount

**Last updated**: 2026-05-21
**Scope**: Docker (T1 sandbox) 의 cwd 절대경로 + bind mount 인프라 fix
**Status**: 운영 중. real Docker sanity check 통과.

원본 RCA 는 [`docs/archive/improvements/`](../archive/improvements/) 에 보존.

---

## 0. 개요

R-sig-detail (Round 13) 가 Phase A signature granularity 를 강화한 후 Round 14
e2e BFS / Segment Tree 실측에서 노출된 Docker 인프라 이슈 2 개. LLM 코드 자체
가 아니라 Docker container 가 host 파일에 접근 못 하는 패턴.

---

## 1. 포함된 fix

| Round | Fix | 원본 RCA | 영향 |
|---|---|---|---|
| 15 | R-docker-workdir | [`2026-05-18_docker-workdir-fix.md`](../archive/improvements/2026-05-18_docker-workdir-fix.md) | DockerRunner cwd 자동 절대화 |
| 16 | R-docker-mount | [`2026-05-18_docker-mount-fix.md`](../archive/improvements/2026-05-18_docker-mount-fix.md) | --tmpfs → -v bind mount 교체 |

---

## 2. 패턴

### 2.1 cwd 절대경로 (Round 15)

증상: Round 14 e2e 에서 sample 전체 RTE — "Docker working directory not absolute".

원인: `RunSpec.cwd: str` 이 relative 일 때 Docker 가 reject. 호출자가 relative
path 넘기는 케이스 존재.

Fix: `DockerRunner.run()` 이 `spec.cwd` 를 `Path(cwd).resolve()` 로 자동 절대화.
`main.py` 도 `OUTPUTS_ROOT` / `WORKDIR_ROOT` 를 `.resolve()`.

### 2.2 bind mount (Round 16)

증상: Round 15 fix 후 재실측 — "python3: can't open file 'solution.py'".

원인: 기존 Docker spec `--tmpfs={cwd}` 가 host 의 cwd (solution.py 가 있는) 를
tmpfs overlay 로 마스크함. 즉 컨테이너에서 solution.py 가 보이지 않음.

Fix: `-v {cwd}:{cwd}:rw` bind mount 로 변경. `--read-only` rootfs 는 유지 (격리
보장). real Docker 환경에서 sanity check 통과.

---

## 3. 운영 시 주의

- **macOS Docker Desktop**: default sharing path 가 `/Users/`. 다른 경로
  (`/opt/`, `/private/tmp/`) 의 workdir 사용 시 user 가 Docker Desktop file
  sharing 설정 추가 필요.
- **Linux**: cgroup permission 필요 (rootless docker 의 경우 추가 설정).
- **CI matrix**: ubuntu-latest 에서 Docker 사용 가능. macOS runner 는 Docker
  미설치이라 T2.5 / T3 fallback.

---

## 4. Rollback trigger (PRINCIPLES.md 룰 5)

- T1 Docker 가 다른 sandbox tier (T2.5 / T3) 대비 quality 우위 없으면 → Docker
  사용 default off, 명시적 `--sandbox docker` 만 사용. 본 두 fix 는 그 시점에
  legacy 로 보존.
- 정상 회복 조건: `make selftest-all` 통과 + e2e Docker 5 algo 실행에서 RTE 0%.

---

## 5. 후속 개선 후보

- Docker rootless 모드 자동 감지 + permission fallback.
- macOS Docker Desktop sharing path 자동 진단 (`docker info` 파싱).
- T1 Docker vs T3 RLIMIT 의 quality / cost 비교 측정 (per-release baseline 의 일부).
