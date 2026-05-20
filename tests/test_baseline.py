"""ipe/baseline/ 단위 테스트.

LLM mock + sandbox 실측. _parse_response 5 branch + run_baseline 통합 path 검증.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from ipe.baseline.runner import _parse_response, run_baseline
from ipe.sandbox.rlimit_runner import RlimitRunner


def _llm_response(content: str, *, in_tok: int = 100, out_tok: int = 200) -> MagicMock:
    chat = MagicMock()
    chat.model = "claude-opus-4-7"
    resp = MagicMock(spec=BaseMessage)
    resp.content = content
    resp.usage_metadata = {"input_tokens": in_tok, "output_tokens": out_tok}
    chat.invoke.return_value = resp
    return chat


VALID_BASELINE_RESPONSE = """```json
{
  "problem_title": "A+B",
  "problem_description": "Two integers sum",
  "constraints": "1<=a,b<=1e9",
  "time_limit_ms": 2000,
  "memory_limit_mb": 256,
  "samples": [
    {"input": "1 2\\n", "expected_output": "3"},
    {"input": "10 20\\n", "expected_output": "30"},
    {"input": "5 7\\n", "expected_output": "12"}
  ]
}
```

```python
a, b = map(int, input().split())
print(a + b)
```
"""

VALID_BASELINE_WITH_WRONG_SAMPLE = """```json
{
  "problem_title": "A+B",
  "problem_description": "...",
  "constraints": "...",
  "time_limit_ms": 2000,
  "memory_limit_mb": 256,
  "samples": [
    {"input": "1 2\\n", "expected_output": "3"},
    {"input": "10 20\\n", "expected_output": "999"}
  ]
}
```

```python
a, b = map(int, input().split())
print(a + b)
```
"""


# =============================================================================
# _parse_response — 5 branches
# =============================================================================


class TestParseResponse:
    def test_valid_response(self) -> None:
        data, code, mode = _parse_response(VALID_BASELINE_RESPONSE)
        assert mode == "ok"
        assert data is not None
        assert code is not None
        assert data["problem_title"] == "A+B"
        assert "print(a + b)" in code
        assert len(data["samples"]) == 3

    def test_unparseable_json(self) -> None:
        data, code, mode = _parse_response("no json here at all")
        assert mode == "unparseable"
        assert data is None
        assert code is None

    def test_non_dict_json(self) -> None:
        data, code, mode = _parse_response("```json\n[1, 2]\n```")
        assert mode == "unparseable"
        assert data is None

    def test_missing_samples_field(self) -> None:
        body = json.dumps({"problem_title": "X"})
        data, _code, mode = _parse_response(f"```json\n{body}\n```")
        assert mode == "no_samples"
        assert data is None

    def test_empty_samples_list(self) -> None:
        body = json.dumps({"problem_title": "X", "samples": []})
        data, _code, mode = _parse_response(f"```json\n{body}\n```")
        assert mode == "no_samples"
        assert data is None

    def test_no_python_fence(self) -> None:
        body: dict[str, Any] = {
            "problem_title": "X",
            "samples": [{"input": "1", "expected_output": "1"}],
        }
        data, code, mode = _parse_response(f"```json\n{json.dumps(body)}\n```")
        assert mode == "no_solution"
        assert data is None
        assert code is None


# =============================================================================
# run_baseline — 통합 (mock LLM + 실제 sandbox)
# =============================================================================


class TestRunBaseline:
    def test_all_samples_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """정상 응답 → sample 3/3 pass → failure_mode='ok'."""
        chat = _llm_response(VALID_BASELINE_RESPONSE)
        monkeypatch.setattr("ipe.baseline.runner.get_chat", lambda *a, **k: chat)

        result = run_baseline("A+B")

        assert result["failure_mode"] == "ok"
        assert result["sample_count"] == 3
        assert result["sample_pass"] == 3
        assert result["sample_fail"] == 0
        assert result["pass_rate"] == 1.0
        assert result["llm_input_tokens"] == 100
        assert result["llm_output_tokens"] == 200

    def test_wrong_sample_marked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sample 1개의 expected가 잘못된 경우 → 1 pass + 1 fail."""
        chat = _llm_response(VALID_BASELINE_WITH_WRONG_SAMPLE)
        monkeypatch.setattr("ipe.baseline.runner.get_chat", lambda *a, **k: chat)

        result = run_baseline("A+B")

        assert result["failure_mode"] == "wrong_sample"
        assert result["sample_count"] == 2
        assert result["sample_pass"] == 1
        assert result["sample_fail"] == 1
        assert result["pass_rate"] == 0.5

    def test_unparseable_skips_sample_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM 응답 parse 실패 → sample 안 돌리고 fail 결과 반환."""
        chat = _llm_response("garbage")
        monkeypatch.setattr("ipe.baseline.runner.get_chat", lambda *a, **k: chat)

        result = run_baseline("BFS")

        assert result["failure_mode"] == "unparseable"
        assert result["sample_count"] == 0
        assert result["pass_rate"] == 0.0
        # LLM call은 일어났음
        assert result["llm_input_tokens"] == 100

    def test_solution_runtime_error_marked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """솔루션 코드가 stderr를 출력하면 fail."""
        broken_response = """```json
{
  "problem_title": "X",
  "problem_description": "...",
  "constraints": "...",
  "time_limit_ms": 2000,
  "memory_limit_mb": 256,
  "samples": [{"input": "1\\n", "expected_output": "1"}]
}
```

```python
raise ValueError("intentional crash")
```
"""
        chat = _llm_response(broken_response)
        monkeypatch.setattr("ipe.baseline.runner.get_chat", lambda *a, **k: chat)

        result = run_baseline("X")

        assert result["failure_mode"] == "runtime_error"
        assert result["sample_pass"] == 0
        assert result["sample_fail"] == 1

    def test_non_python_language_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="language="):
            run_baseline("X", language="java")

    def test_custom_runner_passed_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """runner 명시 시 그대로 사용."""
        chat = _llm_response(VALID_BASELINE_RESPONSE)
        monkeypatch.setattr("ipe.baseline.runner.get_chat", lambda *a, **k: chat)
        custom = RlimitRunner()

        result = run_baseline("A+B", runner=custom)

        assert result["failure_mode"] == "ok"


# =============================================================================
# CLI — basic smoke
# =============================================================================


class TestCLISmoke:
    def test_run_subcommand_outputs_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        chat = _llm_response(VALID_BASELINE_RESPONSE)
        monkeypatch.setattr("ipe.baseline.runner.get_chat", lambda *a, **k: chat)

        from ipe.baseline.__main__ import main
        rc = main(["run", "A+B"])
        captured = capsys.readouterr()

        assert rc == 0
        data = json.loads(captured.out)
        assert data["failure_mode"] == "ok"
        assert data["sample_pass"] == 3

    def test_run_subcommand_writes_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        chat = _llm_response(VALID_BASELINE_RESPONSE)
        monkeypatch.setattr("ipe.baseline.runner.get_chat", lambda *a, **k: chat)
        out_file = tmp_path / "result.json"

        from ipe.baseline.__main__ import main
        rc = main(["run", "A+B", "--out", str(out_file)])
        capsys.readouterr()  # discard

        assert rc == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["sample_pass"] == 3

    def test_run_subcommand_returns_1_on_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],  # noqa: ARG002
    ) -> None:
        chat = _llm_response("garbage")
        monkeypatch.setattr("ipe.baseline.runner.get_chat", lambda *a, **k: chat)

        from ipe.baseline.__main__ import main
        rc = main(["run", "X"])
        assert rc == 1
