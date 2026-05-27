"""SieveVerifier 단위 테스트 (D안 Phase 2b PR-C8)."""

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
from ipe.v1.verifiers import SieveVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N (single integer, 0 <= N <= 10000)",
        output_format="ascending primes <= N, space-separated",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="Sieve of Eratosthenes",
        complexity_target=ComplexityBound(
            time_big_o="O(N log log N)", space_big_o="O(N)"
        ),
        pseudocode="Mark multiples as composite.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.SIEVE,
        title="Sieve of Eratosthenes",
        description="Primes <= N.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="10", expected_output="2 3 5 7"),
            SampleTestCase(input_text="20", expected_output="2 3 5 7 11 13 17 19"),
            SampleTestCase(input_text="2", expected_output="2"),
        ],
    )


def test_passes_with_correct_primes() -> None:
    v = SieveVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["2 3 5 7", "2 3 5 7 11 13 17 19", "2"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert SieveVerifier.target_algorithm is TargetAlgorithm.SIEVE


def test_catches_non_integer_output() -> None:
    v = SieveVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["two three five seven", "2 3 5 7 11 13 17 19", "2"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_int_list"


def test_catches_out_of_range_below_2() -> None:
    v = SieveVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1 2 3 5 7", "2 3 5 7 11 13 17 19", "2"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "all_in_valid_range"


def test_catches_out_of_range_above_n() -> None:
    v = SieveVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["2 3 5 7 11", "2 3 5 7 11 13 17 19", "2"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "all_in_valid_range"


def test_catches_duplicates() -> None:
    v = SieveVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["2 3 3 5 7", "2 3 5 7 11 13 17 19", "2"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "all_strictly_ascending"


def test_catches_descending_order() -> None:
    v = SieveVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["7 5 3 2", "2 3 5 7 11 13 17 19", "2"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "all_strictly_ascending"


def test_catches_missing_prime() -> None:
    v = SieveVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["2 3 7", "2 3 5 7 11 13 17 19", "2"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "matches_trial_division"


def test_catches_composite_included() -> None:
    v = SieveVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["2 3 5 7 9", "2 3 5 7 11 13 17 19", "2"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "matches_trial_division"


def test_n_one_empty_output() -> None:
    v = SieveVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SIEVE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="1", expected_output=""),
            SampleTestCase(input_text="0", expected_output=""),
            SampleTestCase(input_text="5", expected_output="2 3 5"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["", "", "2 3 5"])
    assert violations == []


def test_whitespace_tolerant_multiline_output() -> None:
    v = SieveVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["2\n3\n5\n7", "2 3 5 7 11 13 17 19", "2"],
    )
    assert violations == []


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SIEVE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="5", expected_output="2 3 5"),
            SampleTestCase(input_text="5", expected_output="2 3 5"),
        ],
    )
    v = SieveVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_n_too_large_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SIEVE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="100000", expected_output="x"),
            SampleTestCase(input_text="5", expected_output="2 3 5"),
            SampleTestCase(input_text="5", expected_output="2 3 5"),
        ],
    )
    v = SieveVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_negative_n_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SIEVE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="-5", expected_output="x"),
            SampleTestCase(input_text="5", expected_output="2 3 5"),
            SampleTestCase(input_text="5", expected_output="2 3 5"),
        ],
    )
    v = SieveVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert SieveVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_get_verifier_returns_sieve_after_module_import() -> None:
    register_verifier(SieveVerifier())
    verifier = get_verifier(TargetAlgorithm.SIEVE)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.SIEVE


def test_large_n_within_limit() -> None:
    v = SieveVerifier()
    expected_primes = (
        "2 3 5 7 11 13 17 19 23 29 31 37 41 43 47 53 59 61 67 71 "
        "73 79 83 89 97"
    )
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SIEVE,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="100", expected_output=expected_primes),
            SampleTestCase(input_text="5", expected_output="2 3 5"),
            SampleTestCase(input_text="5", expected_output="2 3 5"),
        ],
    )
    violations = v.verify(
        spec, _design(), _attempt(), sample_outputs=[expected_primes, "2 3 5", "2 3 5"]
    )
    assert violations == []
