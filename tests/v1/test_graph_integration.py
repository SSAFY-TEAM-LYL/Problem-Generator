"""v1 LangGraph integration tests (D안 PR-A3).

mock LLMs + scripted runner + stub verifier 로 4 시나리오:
1. success (한 cycle 통과)
2. retry-then-success (coder 첫 시도 wrong → fix → 통과)
3. budget exhausted (max_iterations 도달)
4. oscillation halt (같은 blocking_signature 2회 → halt)
"""

from __future__ import annotations

from typing import Any

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.graph import build_graph
from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    Invariant,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    TargetAlgorithm,
)
from ipe.v1.state import V1State, initial_state


def _spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="mock dijkstra",
        description="d",
        io_contract=IOContract(input_format="V E s t...", output_format="int"),
        sample_testcases=[
            SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
            SampleTestCase(input_text="3 2 0 2\n0 1 1\n1 2 2", expected_output="3"),
            SampleTestCase(input_text="2 0 0 1", expected_output="-1"),
        ],
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Dijkstra",
        complexity_target=ComplexityBound(
            time_big_o="O((V+E) log V)", space_big_o="O(V+E)"
        ),
        pseudocode="dist[s]=0; pq; relax.",
        invariants=[
            Invariant(kind="non_negative_distance", description="d>=0"),
        ],
    )


def _attempt(code: str = "print(5)", iteration: int = 0) -> SolutionAttempt:
    return SolutionAttempt(code=code, iteration=iteration)


class _FixedArchitectLLM:
    def __init__(self) -> None:
        self.spec = _spec()

    def generate(self, state: V1State) -> ProblemSpec:
        return self.spec


class _FixedDesignerLLM:
    def __init__(self) -> None:
        self.design = _design()

    def generate(self, state: V1State) -> AlgorithmDesign:
        return self.design


class _SequentialCoderLLM:
    """호출 횟수마다 다른 attempt 반환 (retry 시나리오용)."""

    def __init__(self, attempts: list[SolutionAttempt]) -> None:
        self._attempts = list(attempts)
        self.call_count = 0

    def generate(self, state: V1State) -> SolutionAttempt:
        idx = min(self.call_count, len(self._attempts) - 1)
        self.call_count += 1
        return self._attempts[idx]


class _AlwaysOkRunner:
    """sample 별로 정해진 stdout 을 OK 로 반환."""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self.call_count = 0

    def run(self, spec: RunSpec) -> RunResult:
        out = self._outputs[self.call_count % len(self._outputs)]
        self.call_count += 1
        return RunResult(
            status="OK", returncode=0, stdout=out, stderr="", elapsed_ms=5
        )


class _StubVerifier:
    target_algorithm = TargetAlgorithm.DIJKSTRA

    def verify(
        self,
        spec: Any,
        design: Any,
        attempt: Any,
        sample_outputs: Any,
    ) -> list[Any]:
        return []

    def count_engaged_samples(self, spec: Any) -> int:
        return 3


def _verifier_getter(verifier: _StubVerifier) -> Any:
    def get(_algo: TargetAlgorithm) -> _StubVerifier:
        return verifier

    return get


def _build_test_graph(
    *,
    coder_llm: Any,
    runner: Any,
    verifier: _StubVerifier | None = None,
) -> Any:
    return build_graph(
        architect_llm=_FixedArchitectLLM(),
        designer_llm=_FixedDesignerLLM(),
        coder_llm=coder_llm,
        runner=runner,
        verifier_getter=_verifier_getter(verifier or _StubVerifier()),
    )


def _final_state(raw: Any) -> V1State:
    """LangGraph invoke 반환은 dict 또는 BaseModel — V1State 로 normalize."""
    if isinstance(raw, V1State):
        return raw
    return V1State.model_validate(raw)


# ---------- Scenario 1: success on first iteration ----------


def test_success_in_single_iteration() -> None:
    coder = _SequentialCoderLLM([_attempt("print(5)", iteration=0)])
    runner = _AlwaysOkRunner(["5", "3", "-1"])
    graph = _build_test_graph(coder_llm=coder, runner=runner)

    initial = initial_state("run-success", TargetAlgorithm.DIJKSTRA)
    raw_final = graph.invoke(initial)
    final = _final_state(raw_final)

    assert final.final_status == "success"
    assert final.verification is not None
    assert final.verification.overall_pass is True
    assert final.iteration == 1
    assert coder.call_count == 1


# ---------- Scenario 2: retry then success ----------


def test_retry_then_success() -> None:
    """coder 첫 시도 wrong → executor SAMPLE_MISMATCH → coder retry → success."""
    wrong = _attempt("print(999)", iteration=0)
    fixed = _attempt("print(5)", iteration=1)
    coder = _SequentialCoderLLM([wrong, fixed])

    runner = _AlwaysOkRunner(["999", "999", "999", "5", "3", "-1"])

    graph = _build_test_graph(coder_llm=coder, runner=runner)
    initial = initial_state("run-retry", TargetAlgorithm.DIJKSTRA)
    raw_final = graph.invoke(initial)
    final = _final_state(raw_final)

    assert final.final_status == "success"
    assert coder.call_count == 2
    assert len(final.context.iterations) == 2


# ---------- Scenario 3: budget exhausted ----------


def test_budget_exhausted_with_distinct_failures_each_iter() -> None:
    """max_iterations=2 + 각 iter 다른 blocking_signature → osc 안 걸리고 budget."""
    attempts = [_attempt(f"print({100 + i})", iteration=i) for i in range(10)]
    coder = _SequentialCoderLLM(attempts)
    runner = _AlwaysOkRunner(
        [
            "100", "3", "-1",
            "5", "200", "-1",
            "5", "3", "300",
        ]
    )
    graph = _build_test_graph(coder_llm=coder, runner=runner)

    initial = initial_state("run-budget", TargetAlgorithm.DIJKSTRA, max_iterations=2)
    raw_final = graph.invoke(initial)
    final = _final_state(raw_final)

    assert final.final_status == "fail_budget_exhausted"
    assert final.iteration >= 2


# ---------- Scenario 4: oscillation halt ----------


def test_oscillation_halt_on_repeated_signature() -> None:
    """coder 가 같은 wrong 반복 → 같은 sample-0-mismatch sig 2번 → end_oscillation."""
    same_wrong = _attempt("print(999)", iteration=0)
    coder = _SequentialCoderLLM([same_wrong, same_wrong, same_wrong])
    runner = _AlwaysOkRunner(["999", "3", "-1"] * 5)

    graph = _build_test_graph(coder_llm=coder, runner=runner)
    initial = initial_state("run-osc", TargetAlgorithm.DIJKSTRA, max_iterations=8)
    raw_final = graph.invoke(initial)
    final = _final_state(raw_final)

    assert final.final_status == "fail_oscillation"
    assert final.iteration == 2
    assert len(final.context.iterations) == 2
    sigs = [r.blocking_signature for r in final.context.iterations]
    assert sigs == ["sample-0-mismatch", "sample-0-mismatch"]
