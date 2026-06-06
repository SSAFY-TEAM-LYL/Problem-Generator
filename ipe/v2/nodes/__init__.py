"""V2 graph 노드 — blueprint-first B2B 파이프라인 (Phase 3 M3+).

각 노드는 ``V2State → V2State`` factory pattern (v1 nodes 와 동일). LLM 의존성은
Protocol 로 정의, production impl 은 langchain-anthropic ``with_structured_output``
사용. modeling layer(M3 step2)는 책임 분리(Q1): Strategist(Sonnet, 발산 시드) →
Formalizer(Opus, blueprint freeze).
"""

from __future__ import annotations

from .formalizer import (
    AnthropicFormalizerLLM,
    FormalizerLLM,
    make_formalizer_node,
)
from .strategist import (
    AnthropicStrategistLLM,
    StrategistLLM,
    make_strategist_node,
)

__all__ = [
    "AnthropicFormalizerLLM",
    "AnthropicStrategistLLM",
    "FormalizerLLM",
    "StrategistLLM",
    "make_formalizer_node",
    "make_strategist_node",
]
