"""Unit tests for ipe.llm."""

from __future__ import annotations

import pytest

from ipe.llm import (
    ARCHITECT_MODEL,
    CODER_MODEL,
    get_chat,
    parse_json_array_field,
    parse_json_block,
)


class TestGetChat:
    def test_opus_instance(self) -> None:
        chat = get_chat(ARCHITECT_MODEL, max_tokens=1024)
        assert chat.model == ARCHITECT_MODEL

    def test_sonnet_with_temperature(self) -> None:
        chat = get_chat(CODER_MODEL, temperature=0.7)
        assert chat.model == CODER_MODEL
        assert chat.temperature == 0.7

    def test_opus_temperature_silently_dropped(self) -> None:
        # Opus는 temperature 인자를 거부하므로 자동으로 빠짐
        chat = get_chat(ARCHITECT_MODEL, temperature=0.5)
        assert chat.model == ARCHITECT_MODEL


class TestParseJsonBlock:
    def test_fenced_json(self) -> None:
        text = '```json\n{"a": 1, "b": [2, 3]}\n```'
        assert parse_json_block(text) == {"a": 1, "b": [2, 3]}

    def test_unlabeled_fence(self) -> None:
        text = "```\n[1, 2, 3]\n```"
        assert parse_json_block(text) == [1, 2, 3]

    def test_bare_object(self) -> None:
        assert parse_json_block('here {"x": 42} done') == {"x": 42}

    def test_bare_array(self) -> None:
        assert parse_json_block("result: [1, 2, 3]") == [1, 2, 3]

    def test_longest_fence_wins(self) -> None:
        text = (
            "```\n# short\n```\n"
            '```json\n{"real": true, "x": 100}\n```'
        )
        assert parse_json_block(text) == {"real": True, "x": 100}

    def test_empty_text(self) -> None:
        with pytest.raises(ValueError, match="No valid JSON"):
            parse_json_block("")

    def test_no_json(self) -> None:
        with pytest.raises(ValueError, match="No valid JSON"):
            parse_json_block("hello world")


class TestParseJsonArrayField:
    def test_complete_array(self) -> None:
        text = '{"items": [{"a": 1}, {"a": 2}]}'
        assert parse_json_array_field(text, "items") == [{"a": 1}, {"a": 2}]

    def test_truncated_array(self) -> None:
        text = '{"items": [{"a": 1}, {"a": 2}, {"a'
        assert parse_json_array_field(text, "items") == [{"a": 1}, {"a": 2}]

    def test_field_not_found(self) -> None:
        assert parse_json_array_field('{"other": []}', "items") == []

    def test_empty_array(self) -> None:
        text = '{"items": []}'
        assert parse_json_array_field(text, "items") == []

    def test_string_with_braces(self) -> None:
        text = '{"items": [{"key": "with { brace"}]}'
        assert parse_json_array_field(text, "items") == [{"key": "with { brace"}]

    def test_escaped_quote_in_string(self) -> None:
        text = '{"items": [{"k": "say \\"hi\\""}]}'
        assert parse_json_array_field(text, "items") == [{"k": 'say "hi"'}]
