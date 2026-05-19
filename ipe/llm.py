"""Claude (Anthropic) chat wrapper + JSON 응답 파서.

스펙: ARCHITECTURE.md §3.3 (ipe/llm.py — Claude 호출과 JSON 파싱)
모델 매핑 SSOT: ARCHITECTURE.md §3.3.0

- get_chat: model에 따라 동적으로 ChatAnthropic 구성
- parse_json_block: LLM 응답에서 JSON 객체/배열 추출 (펜스 우선)
- parse_json_array_field: truncated 응답에서 완성된 entry만 복구
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_anthropic import ChatAnthropic

# ============================================================================
# Model API IDs — ARCH §3.3.0 매핑 표 SSOT
# ============================================================================

ARCHITECT_MODEL = "claude-opus-4-7"
# M1 (v0.3.0 RFC §M1): AlgorithmDesigner는 algorithm 선택 + pseudocode만 — Sonnet으로
# 충분 (빠르고 cost ↓). Opus만큼 깊은 reasoning 필요 없음.
DESIGNER_MODEL = "claude-sonnet-4-6"
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

    구현은 ARCH §3.3.1을 따라 ``**kwargs`` unpacking 패턴 — mypy strict에서
    ``# type: ignore`` 없이도 통과 (B1 fix, 2026-05-08).
    """
    kwargs: dict[str, Any] = {"model": model, "max_tokens": max_tokens}
    if temperature is not None and model in _TEMPERATURE_CAPABLE:
        kwargs["temperature"] = temperature
    return ChatAnthropic(**kwargs)


# ============================================================================
# JSON 응답 파서
# ============================================================================

# ```json ... ``` 또는 ``` ... ``` 펜스 안의 텍스트 캡처
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def parse_json_block(text: str) -> Any:
    """LLM 응답에서 JSON 객체/배열 추출.

    우선순위:
    1. ``` ```json ... ``` ``` 또는 ``` ``` ... ``` ``` 펜스 안
    2. 가장 바깥 ``{...}`` 또는 ``[...]``

    Raises:
        ValueError: JSON을 찾거나 파싱하지 못한 경우.
    """
    # 1) 펜스 우선 — 가장 큰 펜스(설명 펜스 vs 실제 데이터 구분)
    matches = list(_JSON_FENCE_RE.finditer(text))
    if matches:
        # 가장 긴 펜스 내용 선택 — 설명용 짧은 펜스 회피
        best = max(matches, key=lambda m: len(m.group(1)))
        candidate = best.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass  # fall through to bare-bracket attempt

    # 2) 가장 바깥 { } 또는 [ ] — 둘 다 시도, 더 일찍 시작하는 쪽 우선
    candidates: list[tuple[int, int]] = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidates.append((start, end))
    candidates.sort()  # 더 일찍 시작하는 쪽 먼저 시도

    for start, end in candidates:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            continue

    raise ValueError(f"No valid JSON block found in text (head: {text[:200]!r})")


def parse_json_array_field(text: str, field_name: str) -> list[Any]:
    """truncated 응답에서 ``field_name``의 array entry 중 완성된 것만 복구.

    예시: ``text = '{"adversarial_inputs": [{"input": "1"}, {"input":...'``
    ``field_name = "adversarial_inputs"`` → ``[{"input": "1"}]``

    LLM 출력이 max_tokens에 걸려 array가 닫히지 않을 때 부분 복구.
    """
    # field 이름 패턴 — "<field_name>": [
    field_pattern = re.compile(rf'"{re.escape(field_name)}"\s*:\s*\[')
    m = field_pattern.search(text)
    if not m:
        return []
    return _walk_complete_objects(text, m.end())


def _walk_complete_objects(text: str, start_idx: int) -> list[Any]:
    """``text[start_idx:]``를 한 글자씩 스캔하여 완성된 JSON 객체들 추출.

    문자열 내부의 ``{`` ``}``는 깊이 카운터에 영향 X. 이스케이프 ``\\"``도 처리.
    """
    out: list[Any] = []
    i = start_idx
    n = len(text)

    while i < n:
        # 공백/콤마 건너뛰기
        while i < n and text[i] in " \t\n\r,":
            i += 1
        if i >= n or text[i] == "]":
            break
        if text[i] != "{":
            # 객체가 아닌 토큰 — 스칼라 array는 본 함수의 대상이 아님
            break

        # 중괄호 깊이를 세며 한 객체의 닫는 } 찾기
        depth = 0
        in_str = False
        esc = False
        j = i
        completed = False
        while j < n:
            ch = text[j]
            if esc:
                esc = False
            elif in_str:
                if ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        out.append(json.loads(text[i : j + 1]))
                    except json.JSONDecodeError:
                        return out
                    i = j + 1
                    completed = True
                    break
            j += 1

        if not completed:
            # text 끝까지 닫는 }를 못 찾음 → 미완성 객체. 여기서 중단.
            return out

    return out
