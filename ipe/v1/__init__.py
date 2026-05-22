"""IPE v1 — Detection Backbone + State Refactor (D안 architecture).

v0 (``ipe/``) 와 격리된 새 layer. Phase 1 (PR-A1~A5) 진행 중.

배경/근거:
- 진단: `docs/baseline/v0.3.0-rc1-N3.md` §4.2 (recovery 한계) + §4.4 (subagent
  패턴 정당성 의문).
- 가설: `docs/PRINCIPLES.md` §1 — information bottleneck (자연어 통신 +
  stateless LLM call) 이 80% 천장의 진짜 원인.

D안 가설:
- H1 노드 간 prose → typed structured artifacts 로 fix loop ``budget_exhausted``
  감소.
- H2 algorithm-specific symbolic verifier 가 retry feedback 명료성 ↑.
- H3 IterationContext 누적이 skill amnesia 완화.

Phase 1 (Dijkstra MVR) gate:
- IPE v1 N=3 ≥ 2/3 success → Phase 2 진입.
- N=3 ≤ 0/3 → v1 rewrite kill-switch 발동, archive.
"""
