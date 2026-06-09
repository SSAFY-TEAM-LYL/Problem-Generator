"""v2 입력 생성 — GeneratorContract + io_schema → 결정론적 입력 (Phase 3 M4).

LLM 이 *무엇을* 생성할지(GeneratorContract, step2)를 설계하면, 여기서 *실제 입력*을
**결정론적**으로 만든다(RFC §7: 입력은 schema 에서 결정론 생성 가능). expected 는
미포함 — suite assembler(step4)가 verified golden 실행으로 채운다.
"""

from __future__ import annotations

from .input_gen import generate_inputs

__all__ = ["generate_inputs"]
