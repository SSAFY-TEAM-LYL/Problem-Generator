"""IPE v1 nodes — architect / designer / coder / executor.

각 노드는 ``V1State → V1State`` factory pattern. LLM 의존성은 Protocol 로 정의,
production impl 은 langchain-anthropic ``with_structured_output(Pydantic)`` 사용
(D안 H1 — prose JSON parsing 제거).

graph.py (다음 step) 가 ``make_*_node()`` factory 호출 + LangGraph 등록.
"""

from __future__ import annotations

from .architect import (
    AnthropicArchitectLLM,
    ArchitectLLM,
    make_architect_node,
)
from .coder import (
    AnthropicCoderLLM,
    CoderLLM,
    make_coder_node,
)
from .designer import (
    AnthropicDesignerLLM,
    DesignerLLM,
    make_designer_node,
)
from .executor import (
    ExecutorRunner,
    VerifierGetter,
    make_executor_node,
)
from .reconciler import make_reconciler_node
from .synth_bridge import make_synth_bridge_node
from .synthesis_coder import make_synthesis_coder_node

__all__ = [
    "AnthropicArchitectLLM",
    "AnthropicCoderLLM",
    "AnthropicDesignerLLM",
    "ArchitectLLM",
    "CoderLLM",
    "DesignerLLM",
    "ExecutorRunner",
    "VerifierGetter",
    "make_architect_node",
    "make_coder_node",
    "make_designer_node",
    "make_executor_node",
    "make_reconciler_node",
    "make_synth_bridge_node",
    "make_synthesis_coder_node",
]
