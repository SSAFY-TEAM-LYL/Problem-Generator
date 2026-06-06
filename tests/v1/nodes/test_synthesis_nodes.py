"""synthesis_coder / reconciler 노드 단위 테스트 (Phase 3 M2 step3).

- ``make_synthesis_coder_node``: ``CoderLLM.generate`` → ``SolutionAttempt`` 를
  role/origin 라벨된 ``SolutionCandidate`` (partial dict) 로 wrap.
- ``make_reconciler_node``: ``state.candidates`` + ``spec.sample_testcases`` 입력으로
  ``reconcile()`` 호출 → reconciliation 결과 partial dict.

scripted runner 로 sandbox 없이 결정론 검증 (test_reconcile 패턴 미러).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.nodes.reconciler import make_reconciler_node
from ipe.v1.nodes.synthesis_coder import make_synthesis_coder_node
from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    Invariant,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    SolutionCandidate,
    TargetAlgorithm,
)
from ipe.v1.state import V1State, initial_state


def _spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="t",
        description="d",
        io_contract=IOContract(input_format="i", output_format="o"),
        sample_testcases=[
            SampleTestCase(input_text="i1", expected_output="o1"),
            SampleTestCase(input_text="i2", expected_output="o2"),
            SampleTestCase(input_text="i3", expected_output="o3"),
        ],
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="two_sum",
        complexity_target=ComplexityBound(time_big_o="O(n)", space_big_o="O(n)"),
        pseudocode="hash map.",
        invariants=[Invariant(kind="unique_pair", description="x")],
    )


def _state_with_spec() -> V1State:
    base = initial_state("run-unit", TargetAlgorithm.TWO_SUM)
    return base.model_copy(update={"spec": _spec(), "design": _design()})


class _FixedCoderLLM:
    """고정 code 를 반환하는 mock CoderLLM (state 무시)."""

    def __init__(self, code: str) -> None:
        self._code = code

    def generate(self, state: V1State) -> SolutionAttempt:
        return SolutionAttempt(code=self._code, iteration=0)


class _ScriptedRunner:
    """fn(code, stdin) -> (status, stdout) 로 RunResult 생성 (deterministic)."""

    def __init__(self, fn: Callable[[str, str], tuple[str, str]]) -> None:
        self._fn = fn

    def run(self, spec: RunSpec) -> RunResult:
        code = (Path(spec.cwd) / "sol.py").read_text(encoding="utf-8")
        status, stdout = self._fn(code, spec.stdin)
        return RunResult(
            status=status,  # type: ignore[arg-type]
            returncode=0 if status == "OK" else 1,
            stdout=stdout,
            stderr="" if status == "OK" else "boom",
            elapsed_ms=1,
        )


def _by_marker(code: str, stdin: str) -> tuple[str, str]:
    if "CRASH" in code:
        return ("RTE", "")
    if "WRONG" in code:
        return ("OK", f"wrong-{stdin}")
    return ("OK", f"ans-{stdin}")


# ---------- synthesis_coder ----------


def test_synthesis_coder_wraps_attempt_into_candidate() -> None:
    node = make_synthesis_coder_node(
        _FixedCoderLLM("# golden code"), role="golden", origin="opus", fanout_index=2
    )
    out = node(_state_with_spec())

    assert set(out.keys()) == {"candidates"}
    cands = out["candidates"]
    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c, SolutionCandidate)
    assert c.role == "golden"
    assert c.origin == "opus"
    assert c.code == "# golden code"
    assert c.fanout_index == 2


def test_synthesis_coder_brute_role_defaults_index_zero() -> None:
    node = make_synthesis_coder_node(
        _FixedCoderLLM("# naive"), role="brute", origin="naive"
    )
    c = node(_state_with_spec())["candidates"][0]
    assert c.role == "brute"
    assert c.origin == "naive"
    assert c.fanout_index == 0


def test_synthesis_coder_requires_spec_and_design() -> None:
    node = make_synthesis_coder_node(
        _FixedCoderLLM("x"), role="golden", origin="o"
    )
    bare = initial_state("r", TargetAlgorithm.TWO_SUM)  # spec/design 없음
    with pytest.raises(ValueError, match="spec"):
        node(bare)


# ---------- reconciler ----------


def test_reconciler_node_adopts_canonical_when_all_agree() -> None:
    state = _state_with_spec().model_copy(
        update={
            "candidates": [
                SolutionCandidate(
                    role="golden", origin="opus", code="# GOLDEN", fanout_index=0
                ),
                SolutionCandidate(role="brute", origin="naive", code="# BRUTE"),
            ]
        }
    )
    out = make_reconciler_node(_ScriptedRunner(_by_marker))(state)

    assert set(out.keys()) == {"reconciliation"}
    r = out["reconciliation"]
    assert r.all_agree is True
    assert r.adopted_origin == "opus"
    assert r.canonical_code == "# GOLDEN"
    assert r.candidate_count == 2


def test_reconciler_node_rejects_on_disagreement() -> None:
    state = _state_with_spec().model_copy(
        update={
            "candidates": [
                SolutionCandidate(
                    role="golden", origin="opus", code="# GOLDEN", fanout_index=0
                ),
                SolutionCandidate(role="brute", origin="naive", code="# WRONG"),
            ]
        }
    )
    r = make_reconciler_node(_ScriptedRunner(_by_marker))(state)["reconciliation"]
    assert r.all_agree is False
    assert r.canonical_code is None


def test_reconciler_requires_spec() -> None:
    bare = initial_state("r", TargetAlgorithm.TWO_SUM)  # spec 없음
    with pytest.raises(ValueError, match="spec"):
        make_reconciler_node(_ScriptedRunner(_by_marker))(bare)
