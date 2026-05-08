"""Claude (Anthropic) chat wrapper + JSON 응답 파서.

스펙: ARCHITECTURE.md §3.3 (ipe/llm.py — Claude 호출과 JSON 파싱)
모델 매핑 SSOT: ARCHITECTURE.md §3.3.0

P2.1: get_chat — model에 따라 동적으로 ChatAnthropic 구성.
P2.2: parse_json_block, parse_json_array_field (다음 sub-task에서 추가).
"""

from __future__ import annotations

from langchain_anthropic import ChatAnthropic

# ============================================================================
# Model API IDs — ARCH §3.3.0 매핑 표 SSOT
# ============================================================================

ARCHITECT_MODEL = "claude-opus-4-7"
CODER_MODEL = "claude-sonnet-4-6"
AUDITOR_MODEL = "claude-opus-4-7"
GENERATOR_MODEL = "claude-opus-4-7"
EVALUATOR_MODEL = "claude-opus-4-7"

# Opus 4.7은 temperature 인자를 거부 (extended thinking 모델 특성).
# Sonnet 4.6 등 standard 모델만 temperature 지원.
_TEMPERATURE_CAPABLE: frozenset[str] = frozenset({CODER_MODEL})


def get_chat(
    model: str,
    temperature: float | None = None,
    max_tokens: int = 4096,
) -> ChatAnthropic:
    """Claude chat client를 model에 맞춰 동적으로 구성한다.

    ``temperature``는 모델이 지원할 때만 전달 — Opus는 거부.
    API 키는 ``langchain-anthropic``이 ``ANTHROPIC_API_KEY`` 환경변수에서 자동 로드.
    """
    if temperature is not None and model in _TEMPERATURE_CAPABLE:
        return ChatAnthropic(
            model=model,  # type: ignore[call-arg]
            max_tokens=max_tokens,
            temperature=temperature,
        )
    return ChatAnthropic(
        model=model,  # type: ignore[call-arg]
        max_tokens=max_tokens,
    )
