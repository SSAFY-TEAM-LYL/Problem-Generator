"""HeapVerifier 단위 테스트 (D안 Phase 2c PR-D4)."""

from __future__ import annotations

from ipe.v1.schema import (
    AlgorithmDesign,
    ComplexityBound,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    SolutionAttempt,
    TargetAlgorithm,
)
from ipe.v1.verifiers import HeapVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N + N ops (P x | O)",
        output_format="pop op 마다 한 줄, popped value",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Min-Heap",
        complexity_target=ComplexityBound(time_big_o="O(N log N)", space_big_o="O(N)"),
        pseudocode="binary heap: sift up on push, sift down on pop.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.HEAP,
        title="Min-Heap",
        description="priority queue",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="5\nP 5\nP 3\nO\nP 7\nO",
                expected_output="3\n5",
            ),
            SampleTestCase(
                input_text="4\nP 1\nP 2\nO\nO",
                expected_output="1\n2",
            ),
            SampleTestCase(
                input_text="3\nP 10\nP -5\nO",
                expected_output="-5",
            ),
        ],
    )


def test_passes_with_correct_pops() -> None:
    v = HeapVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["3\n5", "1\n2", "-5"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert HeapVerifier.target_algorithm is TargetAlgorithm.HEAP


def test_catches_wrong_pop_count() -> None:
    v = HeapVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["3", "1\n2", "-5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_count_matches_pops"


def test_catches_non_integer_output() -> None:
    v = HeapVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["three\nfive", "1\n2", "-5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_count_matches_pops"


def test_catches_popped_value_not_in_pushes() -> None:
    v = HeapVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["99\n5", "1\n2", "-5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "all_popped_in_pushed_multiset"


def test_catches_wrong_pop_order_not_min_first() -> None:
    v = HeapVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["5\n3", "1\n2", "-5"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "matches_naive_min_heap_golden"


def test_negative_values_supported() -> None:
    v = HeapVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.HEAP,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3\nP -3\nP -7\nO", expected_output="-7"),
            SampleTestCase(input_text="3\nP -3\nP -7\nO", expected_output="-7"),
            SampleTestCase(input_text="3\nP -3\nP -7\nO", expected_output="-7"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["-7"] * 3)
    assert violations == []


def test_duplicate_values_supported() -> None:
    v = HeapVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.HEAP,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="5\nP 5\nP 5\nP 5\nO\nO",
                expected_output="5\n5",
            ),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["5\n5", "1", "1"])
    assert violations == []


def test_only_pushes_no_pops_empty_output() -> None:
    v = HeapVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.HEAP,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3\nP 1\nP 2\nP 3", expected_output=""),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["", "1", "1"])
    assert violations == []


def test_pop_empty_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.HEAP,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="2\nO\nP 1", expected_output="x"),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
        ],
    )
    v = HeapVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.HEAP,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
        ],
    )
    v = HeapVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_n_too_large_silent_skip() -> None:
    n_count = 1500
    ops_text = "\n".join("P 1" for _ in range(n_count))
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.HEAP,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text=f"{n_count}\n{ops_text}", expected_output="x"),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
        ],
    )
    v = HeapVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert HeapVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_get_verifier_returns_heap_after_module_import() -> None:
    register_verifier(HeapVerifier())
    verifier = get_verifier(TargetAlgorithm.HEAP)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.HEAP


def test_interleaved_push_pop_correctness() -> None:
    """Push 5, pop 5, push 3+7, pop 3, pop 7."""
    v = HeapVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.HEAP,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(
                input_text="6\nP 5\nO\nP 3\nP 7\nO\nO",
                expected_output="5\n3\n7",
            ),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
            SampleTestCase(input_text="2\nP 1\nO", expected_output="1"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["5\n3\n7", "1", "1"])
    assert violations == []
