"""IPE v2 — B2B blueprint-first 파이프라인 (Phase 3 M3+).

canonical(``ipe/v1``, mode=canonical, 91.2% anchor)과 분리된 **fresh 공간**
(`CANONICAL.md`). 검증 해자 — typed 계약(``ipe.v1.schema``), symbolic verifier
(``ipe.v1.verifiers``), differential/metamorphic/reconcile(``ipe.v1.verification``),
sandbox(``ipe.sandbox``) — 는 **재사용**하고, 그 위 토폴로지/state/node 를
blueprint-first 로 새로 짠다 (RFC §3 "계약·검증은 유지, 토폴로지만 재작성").

blueprint-first 흐름: Strategist → Formalizer(blueprint FREEZE) → Solution Synthesis
→ Verification → Narrative(late, 은닉 렌더) → Faithfulness(round-trip) → QA.
"""

from __future__ import annotations
