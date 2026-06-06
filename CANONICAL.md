# Canonical Pipeline — 보존 자산 (Preserved Asset)

> **canonical = 실측으로 유의미한 결과를 낸 유일한 파이프라인.** 동결(freeze)하여 보관한다.
> B2B(Phase 3 / M3+) 작업은 `ipe/v2/` 의 **fresh 공간**에서 이 검증 해자를 재사용해 진행한다.

## 무엇인가

`ipe/v1/` 의 linear 파이프라인 — **B2C 토픽드릴(topic-drill)** 모드:

```
architect → designer → coder → executor → record → router(fix-loop)
(target_algorithm 명시 → ProblemSpec 직접 생성)
```

코드상 진입점: `ipe.v1.graph.build_graph(mode="canonical")` (기본값) · CLI `ipe-v1 --algorithm <algo>`.

## 왜 보존하는가

- **실측 anchor**: pass rate **91.2%**, **19 algorithms**, `v1.0` 출시 (anchor freeze 완료).
- toy 수준(알고리즘 명시)이지만, **측정으로 검증된 유일한 산출물**이다. B2B 은닉 파이프라인(M3)은 별도 신규 anchor(0부터)로 분리 측정한다 — 91.2% 는 canonical 채점표이지 은닉 문제의 채점표가 아니다.

## 앵커 / 복구 지점

| ref | commit | 내용 |
|---|---|---|
| `v1.0` | `a55cfd0` | 순수 canonical (M2/M3 이전, 91.2% anchor) |
| `canonical-stable` | (본 보관 시점) | canonical + M2 full + M3 step1 포함 fork 기준점 |

복구: `git checkout v1.0` (순정 canonical) 또는 `git checkout canonical-stable` (fork 기준점).

## 검증 해자 (v2 가 재사용)

canonical 의 가치는 검증 해자에 있으며, 이는 B2B(v2)가 **그대로 import 재사용**한다 (RFC §3 "계약·검증은 유지, 토폴로지만 재작성"):

- `ipe/v1/schema/` — typed artifact 계약 (ProblemSpec / SolutionAttempt / blueprint 등)
- `ipe/v1/verifiers/` — symbolic verifier 19종 (Tier A)
- `ipe/v1/verification/` — differential / metamorphic / reconcile / tier (Tier B)
- `ipe/sandbox/` — 격리 실행 (이미 공용)

## 동결 정책 (freeze policy)

1. **canonical 경로(`mode="canonical"`) 는 동결.** 수정 시 91.2% anchor 를 N≥3 재측정하지 않는 한 건드리지 않는다.
2. **B2B / Phase 3 (M3+) 작업은 `ipe/v2/` 에서** 진행한다 — fresh graph/state/nodes(blueprint-first 모델링), 해자는 `ipe/v1`·`ipe/sandbox` 에서 재사용.
3. `ipe/v1/` 은 canonical 의 집(home) + 해자 소스로 유지된다 (현재 v1 에 잔존하는 M2 full / M3 step1 실험 코드는 v2 로 점진 이관/대체될 수 있다).

## 관련 문서

- RFC: `docs/rfc/phase3_agentic-graph-rearchitecture.md` (메인) · `docs/rfc/phase3_blueprint-first-generation.md` (생성 순서 — blueprint-first 채택)
