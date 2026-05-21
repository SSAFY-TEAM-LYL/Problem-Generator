# R-gen-cap — Generator Hard Cap Validator (결정적 차단)

**Date**: 2026-05-18 (Round 11)
**Scope**: v0.2.1 결정적 fix sprint — 두 번째 P0 항목 (R-osc-break 후속)
**Related**: CHANGES.md §16.2, REQUIREMENTS.md §5.3 (알려진 한계),
`docs/improvements/2026-05-14_sandbox-infra-rca.md` §D.5,
`docs/improvements/2026-05-18_osc-break-deterministic.md` (paired fix)

---

## 1. 문제 정의

### 1.1 관찰된 증상

Round 10 (Sprint 4) 종료 시점 e2e 매트릭스 (Run 9~12) — Segment Tree 케이스:

| Case | Run 9 | Run 10 | Run 11 | Run 12 | 안정성 |
|---|---|---|---|---|---|
| Segment Tree | FAIL | FAIL | FAIL | FAIL | **0/4** |

trace 공통 패턴:

```
generator → 5 scripts (LLM이 N=200000 + M=200000 stress 시도)
Executor Phase C → 5 (gen, seed) tasks 실행
  gen_max_stress(seed=1) → stdout 2.0+ MB → truncated → "gen_fail"
  gen_max_stress(seed=2) → 같음
  gen_stress_2(seed=1)   → 같음
  ... (전체 25 tasks 중 절반 이상 gen_fail)
decision → last_failed_node="generator" (gen_fail 우세)
generator → LLM 재호출 → 거의 같은 패턴 재생성
... (generator budget 2 소진 → budget_exhausted)
```

배열 N 크기 + 쿼리 M 크기가 둘 다 최대로 잡히면 stdout이 2~4 MB가 되어
`MAX_GENERATED_INPUT_BYTES = 2 * 1024 * 1024` (= 2 MB) cap 초과.

### 1.2 기존 메커니즘이 막지 못한 이유

| 메커니즘 | 방식 | 한계 |
|---|---|---|
| Phase C `_run_generator` | sandbox에 `max_stdout_bytes=cap` 전달 → truncate 감지 | sandbox 내부 fail. Executor가 매번 다 돌고서야 generator로 라우팅 |
| R3 prompt 가이드 | "총 출력 byte 사전 계산" + N+M 예시 | LLM이 실측 없이 정확한 추정 못 함 — int range만 살짝 줄여도 여전히 cap 초과 |
| R10 OLE 한도 (5MB→2MB) | sandbox-side enforce | 동일. prompt-only 가이드는 LLM 응답 변동성 통제 못 함 |
| W4 prompt (oscillation 방지) | "이전과 다른 카테고리 사용" | LLM이 카테고리 이름만 바꾸고 N+M 패턴 그대로 |

**근본 한계**: R3는 사후에야 발견되는 size 위반 — Generator가 응답한 후
Executor Phase C가 다 돌아야 알 수 있다. R-gen-cap은 응답 직후 실측으로
즉시 차단.

---

## 2. 해법 — `_validate_generator_caps` + `generator.run` 통합

### 2.1 사전 검증 함수 (`ipe.nodes.generator._validate_generator_caps`)

```python
def _validate_generator_caps(
    generators: list[dict[str, Any]],
    runner: SandboxedRunner,
    workdir_root: Path,
) -> str | None:
    if not generators:
        return None

    work_dir = workdir_root / f"gencap_{uuid.uuid4().hex[:8]}"
    work_dir.mkdir(parents=True, exist_ok=True)
    cap = MAX_GENERATED_INPUT_BYTES

    rejects: list[str] = []
    for g in generators:
        seeds = g.get("seeds") or []
        if not seeds:
            continue
        seed = int(seeds[0])
        name = str(g.get("name") or "unnamed")
        (work_dir / f"{name}.py").write_text(g.get("code") or "", "utf-8")
        spec = RunSpec(
            cmd=["python3", f"{name}.py", str(seed)],
            cwd=str(work_dir),
            time_limit_ms=GENERATOR_TIMEOUT_MS,
            memory_limit_mb=GENERATOR_MEMORY_LIMIT_MB,
            max_stdout_bytes=cap,
        )
        res = runner.run(spec)
        if res.status == "OK" and not res.truncated_stdout:
            continue
        if res.status == "OLE" or res.truncated_stdout:
            rejects.append(f"'{name}' (seed={seed}) exceeded cap: ...")
        else:
            rejects.append(f"'{name}' (seed={seed}) {res.status}: ...")

    if not rejects:
        return None
    return "R-gen-cap pre-validation rejected ...\n- " + "\n- ".join(rejects)
```

**조건 표**:

| status | truncated_stdout | 처리 |
|---|---|---|
| OK | False | 통과 |
| OK | True | reject (cap 초과로 truncate) |
| OLE | * | reject (size 초과) |
| RTE / TLE / MLE / SANDBOX_ERROR | * | reject (script 오류) |

**중요 설계**:
- 첫 seed만 사용 (전체 seed 검증은 Phase C에서) — 비용 ↓
- 모든 generator를 다 실행 후 한 번에 reject 목록 보고 (early exit 금지)
- 통과한 generator는 feedback에 언급 안 함 (LLM이 그것까지 다시 쓰지 않도록)
- workdir은 `workdir_root/gencap_<uuid>/` — Executor workdir와 분리

### 2.2 `generator.run` 통합

```python
def run(
    state: ProblemState,
    *,
    tracker: LLMCallTracker,
    runner: SandboxedRunner | None = None,
    workdir_root: Path | None = None,
) -> ProblemState:
    # ... LLM 호출 + _parse ...
    if len(generators) < MIN_GENERATORS:
        return _route_back(state, calls, "...")
    if runner is not None:
        wd = workdir_root or Path("workdir")
        wd.mkdir(parents=True, exist_ok=True)
        cap_reject = _validate_generator_caps(generators, runner, wd)
        if cap_reject:
            return _route_back(state, calls, cap_reject)
    return {**state, ..., "generators": generators, ...}
```

- `runner=None` → 검증 skip (단위 테스트 호환, 기존 integration helper 무영향)
- `graph.py`에서 `partial(generator.run, tracker=tracker, runner=runner, workdir_root=workdir_root)`
  로 주입

---

## 3. 우선순위 + 비용

### 3.1 흐름 비교

**Before (R3 prompt-only)**:
```
generator → LLM 응답 → Executor → Phase C (5×5 seed) → 25 sandbox call → fail → generator
                                                              ^^^^^^^^^^^^^^^^^^^^^^^^
                                                              비용 ↑ + fail 알아내기 늦음
```

**After (R-gen-cap)**:
```
generator → LLM 응답 → R-gen-cap (5 sandbox call) → reject → generator
                              ^^^^^^^^^^^^^^^^^^^^^
                              비용 ↓ + 즉시 정확한 feedback
```

비용:
- 5 generator × 1 seed = 5 sandbox call ~ 1~3초 (각 generator script가 stress
  output까지 만들어내려면 약간 시간 소요)
- 통과 시: 추가 비용 1~3초 + Phase C가 정상 진행
- reject 시: Executor 진입 안 함 → Phase C 25 call 절약 (5~15초 절감)

### 3.2 라우팅 영향

R-gen-cap 발동 시 `_route_back` → `last_failed_node="generator"` →
`_decision`이 generator budget 차감 → 다음 cycle generator 재진입. 기존
budget 흐름 그대로 (특별 라우팅 없음).

---

## 4. 테스트 (+9)

`tests/test_generator_cap.py` (신규 — `_FakeRunner` 결정적 mock):

| Test | 검증 |
|---|---|
| `test_empty_generators_returns_none` | 빈 list → None |
| `test_all_under_cap_returns_none` | 모두 OK → None, 모두 1회씩 호출 |
| `test_single_cap_exceed_reports_size` | OLE 1개 → feedback에 이름 + cap 포함 |
| `test_multiple_cap_exceeds_all_reported` | OLE 2개 → 둘 다 보고, early exit 없음 |
| `test_rte_treated_as_reject` | RTE → reject (script 오류) |
| `test_skips_generators_without_seeds` | seeds 빈 generator → skip |
| `test_runner_called_with_first_seed` | spec.cmd에 첫 seed 값 |
| `test_generator_script_written_to_workdir` | 코드가 .py로 disk write |
| `test_ole_with_large_stdout_reports_actual_size` | OLE + 부분 stdout → 보고 |

전체 회귀: **275 passed + 3 skipped** (이전 266 + 본 PR +9).

---

## 5. 한계 + 후속

- **첫 seed 한 번만 실행**: 다른 seed에서 더 큰 출력 가능성. Phase C가
  fallback으로 잡으므로 안전망 유지. R-gen-cap은 cap 초과의 "최저
  bar"만 결정적으로 차단.
- **R-osc-break과 페어**: 두 P0 fix가 함께 적용되어야 e2e 5/5 가능성.
  R-osc-break이 architect oscillation, R-gen-cap이 generator
  oscillation을 각각 차단.
- **Segment Tree e2e 실측**: v0.2.1 release 검증 시점에 5회 run.
- **stdin 정확성 검증**: R-gen-cap은 size만 검증. 출력이 문제 input 형식에
  맞는지는 Phase B의 `_validate_input_against_constraints`가 별도로.
- **첫 seed가 작은 N**: LLM이 `seed=1`은 small case로 짠 경우 cap 검증
  통과해도 큰 seed에서 fail 가능. 다행히 generator template의
  `_BLOCK_RE`가 stress 카테고리는 별도 generator로 분리 유도 →
  MAX_STRESS generator의 첫 seed도 대부분 큰 N 생성.
