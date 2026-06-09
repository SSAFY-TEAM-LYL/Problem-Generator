"""V2 graph 노드 — blueprint-first B2B 파이프라인 (Phase 3 M3+).

각 노드는 ``V2State → V2State`` factory pattern (v1 nodes 와 동일). LLM 의존성은
Protocol 로 정의, production impl 은 langchain-anthropic ``with_structured_output``
사용. modeling layer(M3 step2)는 책임 분리(Q1): Strategist(Sonnet, 발산 시드) →
Formalizer(Opus, blueprint freeze).
"""

from __future__ import annotations

from .faithfulness import (
    AnthropicFaithfulnessLLM,
    FaithfulnessLLM,
    make_faithfulness_node,
)
from .formalizer import (
    AnthropicFormalizerLLM,
    FormalizerLLM,
    make_formalizer_node,
)
from .generator_designer import (
    AnthropicGeneratorDesignerLLM,
    GeneratorDesignerLLM,
    make_generator_designer_node,
)
from .narrative import (
    AnthropicNarrativeLLM,
    NarrativeLLM,
    make_narrative_node,
)
from .spec_bridge import (
    AnthropicSpecBridgeLLM,
    SpecBridgeLLM,
    make_spec_bridge_node,
)
from .strategist import (
    AnthropicStrategistLLM,
    StrategistLLM,
    make_strategist_node,
)

__all__ = [
    "AnthropicFaithfulnessLLM",
    "AnthropicFormalizerLLM",
    "AnthropicGeneratorDesignerLLM",
    "AnthropicNarrativeLLM",
    "AnthropicSpecBridgeLLM",
    "AnthropicStrategistLLM",
    "FaithfulnessLLM",
    "FormalizerLLM",
    "GeneratorDesignerLLM",
    "NarrativeLLM",
    "SpecBridgeLLM",
    "StrategistLLM",
    "make_faithfulness_node",
    "make_formalizer_node",
    "make_generator_designer_node",
    "make_narrative_node",
    "make_spec_bridge_node",
    "make_strategist_node",
]
