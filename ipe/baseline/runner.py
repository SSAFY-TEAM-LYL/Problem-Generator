"""Baseline runner — 1 Opus call로 problem + sample + solution + verification.

설계 결정:
- **1 LLM call**: architect + coder + sample-expected-computation을 같은 응답
  안에서 self-consistent 하게 생성. IPE 의 multi-mechanism (7 노드) 와 quality
  비교 가능.
- **Sample-only verification**: Phase B/C generator/adversarial 은 baseline scope
  밖. IPE 만의 가치 (검증 layer) 와 분리해서 비교.
- **Sandbox = RlimitRunner**: Docker 안 써도 됨 (단순 sample run, 30초 cap).
  IPE 와 같은 runner 면 비교 공정.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ipe.llm import ARCHITECT_MODEL, get_chat
from ipe.sandbox.rlimit_runner import RlimitRunner
from ipe.sandbox.runner import RunSpec

BASELINE_MODEL = ARCHITECT_MODEL  # Opus — IPE 의 architect 와 같은 capability bar


class BaselineResult(TypedDict, total=False):
    """단일 baseline run 결과."""

    algorithm: str
    language: str
    title: str | None
    sample_count: int
    sample_pass: int
    sample_fail: int
    # failure_mode values: "ok" | "unparseable" | "no_solution" | "no_samples"
    # | "wrong_sample" | "runtime_error"
    failure_mode: str
    pass_rate: float  # sample_pass / sample_count (0.0~1.0)
    llm_input_tokens: int
    llm_output_tokens: int
    notes: str


SYSTEM_PROMPT = """You are a master competitive programming author + solver.

For a given target algorithm, produce a SINGLE response containing:
1. **Problem statement** (markdown, Korean OK).
2. **Constraints** (time_limit_ms, memory_limit_mb, variable ranges).
3. **3-5 sample testcases** — for EACH sample, mentally simulate your solution
   on that input and write the EXACT expected_output you computed. Do NOT guess.
4. **Python solution** — complete runnable code that reads from stdin, writes
   to stdout. Use buffered IO (`sys.stdin.buffer.read()`) for large input.

The samples and the solution MUST be consistent: running your solution on
sample.input MUST produce sample.expected_output. If you're unsure of the
output, simulate step-by-step before writing.

Output format — TWO blocks in this order:

First, a JSON block wrapped in ```json fence:
```json
{
  "problem_title": "...",
  "problem_description": "Markdown body (Korean OK)",
  "constraints": "1 ≤ N ≤ ..., 시간 2초, 메모리 256MB",
  "time_limit_ms": 2000,
  "memory_limit_mb": 256,
  "samples": [
    {"input": "...", "expected_output": "..."},
    ...
  ]
}
```

Then, the Python solution wrapped in ```python fence:
```python
import sys
data = sys.stdin.buffer.read().split()
# ... your solution ...
```
"""

USER_TEMPLATE = """Target algorithm: **{algorithm}**

Design a NEW problem exercising this algorithm. Output the JSON + Python blocks.
"""


_FENCE_PY_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)
_JSON_FENCE_START_RE = re.compile(r"```json\s*\n")


def _extract_json_balanced(content: str) -> tuple[dict[str, Any] | None, int]:
    """JSON fence 시작 후, brace-balanced 로 JSON object 추출.

    문제: 일반 fence-based non-greedy 매치는 JSON 안에 markdown triple-backtick
    펜스 (예: problem_description 의 input/output 예시) 가 있으면 거기서 잘림 →
    unparseable.

    해법: json fence 시작 위치 찾고, 그 직후 ``{`` 부터 brace count 0 으로
    돌아오는 곳까지 raw JSON 으로 parse. 문자열 내부의 ``{``/``}`` 는 무시.

    Returns:
        (parsed_dict, json_end_index). 실패 시 (None, -1).
    """
    m = _JSON_FENCE_START_RE.search(content)
    if m is None:
        return None, -1
    # 펜스 시작 직후의 ``{`` 위치
    json_start = content.find("{", m.end())
    if json_start == -1:
        return None, -1

    depth = 0
    in_str = False
    esc = False
    for i in range(json_start, len(content)):
        ch = content[i]
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
                json_end = i + 1
                try:
                    data = json.loads(content[json_start:json_end])
                except json.JSONDecodeError:
                    return None, -1
                return data if isinstance(data, dict) else None, json_end
    return None, -1


def _parse_response(content: str) -> tuple[dict[str, Any] | None, str | None, str]:
    """(json_data, python_code, failure_mode). failure_mode='ok' 면 정상."""
    data, json_end = _extract_json_balanced(content)
    if data is None:
        return None, None, "unparseable"
    if "samples" not in data:
        return None, None, "no_samples"
    samples = data["samples"]
    if not isinstance(samples, list) or not samples:
        return None, None, "no_samples"

    # Python solution 은 JSON 펜스 닫힌 이후에 있어야 함 (안에 ``` 있어도 무시).
    tail = content[json_end:] if json_end > 0 else content
    py_match = _FENCE_PY_RE.search(tail)
    if py_match is None:
        return None, None, "no_solution"
    code = py_match.group(1)

    return data, code, "ok"


def _run_sample(
    code: str, stdin_text: str, *, runner: RlimitRunner, workdir: Path,
) -> tuple[str, str]:
    """Sample 1개 실행. (stdout, stderr) 반환."""
    solution_path = workdir / "solution.py"
    solution_path.write_text(code, encoding="utf-8")
    spec = RunSpec(
        cmd=["python3", "solution.py"],
        cwd=str(workdir),
        stdin=stdin_text,
        time_limit_ms=5000,  # baseline 측정용 — IPE 보다 넉넉히
        memory_limit_mb=512,
    )
    result = runner.run(spec)
    return result.stdout, result.stderr


def run_baseline(
    algorithm: str,
    *,
    language: str = "python",
    runner: RlimitRunner | None = None,
) -> BaselineResult:
    """1 baseline measurement: 1 LLM call + sample 실행.

    Args:
        algorithm: target algorithm name (e.g. "BFS", "Two Sum").
        language: "python" only for now.
        runner: sandbox runner. None → RlimitRunner().

    Returns:
        BaselineResult dict.
    """
    if language != "python":
        raise NotImplementedError(f"baseline language={language!r} not supported yet")

    if runner is None:
        runner = RlimitRunner()

    chat = get_chat(BASELINE_MODEL, max_tokens=4096)
    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=USER_TEMPLATE.format(algorithm=algorithm)),
    ]
    resp = chat.invoke(messages)
    content = str(resp.content)
    usage = getattr(resp, "usage_metadata", None) or {}
    in_tok = int(usage.get("input_tokens", 0))
    out_tok = int(usage.get("output_tokens", 0))

    data, code, fmode = _parse_response(content)
    if data is None or code is None or fmode != "ok":
        return {
            "algorithm": algorithm,
            "language": language,
            "title": None,
            "sample_count": 0,
            "sample_pass": 0,
            "sample_fail": 0,
            "failure_mode": fmode,
            "pass_rate": 0.0,
            "llm_input_tokens": in_tok,
            "llm_output_tokens": out_tok,
            "notes": f"LLM response parse failed: {fmode}",
        }

    samples = data["samples"]
    sample_count = len(samples)
    sample_pass = 0
    sample_fail = 0
    failures: list[str] = []
    runtime_errors = 0

    with tempfile.TemporaryDirectory(prefix="baseline_") as tmp:
        wd = Path(tmp)
        for i, tc in enumerate(samples):
            inp = str(tc.get("input", ""))
            expected = str(tc.get("expected_output", "")).rstrip()
            try:
                stdout, stderr = _run_sample(code, inp, runner=runner, workdir=wd)
            except Exception as e:  # noqa: BLE001 — sandbox 어떤 예외든 fail로 카운트
                sample_fail += 1
                runtime_errors += 1
                failures.append(f"sample {i}: runner exception {type(e).__name__}: {e}")
                continue
            if stderr.strip():
                sample_fail += 1
                runtime_errors += 1
                failures.append(f"sample {i}: stderr {stderr[:80]!r}")
                continue
            actual = stdout.rstrip()
            if actual == expected:
                sample_pass += 1
            else:
                sample_fail += 1
                failures.append(
                    f"sample {i}: expected={expected[:40]!r} actual={actual[:40]!r}"
                )

    failure_mode = "ok" if sample_fail == 0 else (
        "runtime_error" if runtime_errors == sample_count else "wrong_sample"
    )

    return {
        "algorithm": algorithm,
        "language": language,
        "title": str(data.get("problem_title") or ""),
        "sample_count": sample_count,
        "sample_pass": sample_pass,
        "sample_fail": sample_fail,
        "failure_mode": failure_mode,
        "pass_rate": (sample_pass / sample_count) if sample_count else 0.0,
        "llm_input_tokens": in_tok,
        "llm_output_tokens": out_tok,
        "notes": "; ".join(failures) if failures else "",
    }
