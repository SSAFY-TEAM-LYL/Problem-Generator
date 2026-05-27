"""StringMatchVerifier 단위 테스트 (D안 Phase 2b PR-C6)."""

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
from ipe.v1.verifiers import StringMatchVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="text + pattern (2 lines, no whitespace)",
        output_format="single integer — 1-indexed first occurrence or -1",
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="KMP",
        complexity_target=ComplexityBound(time_big_o="O(N+M)", space_big_o="O(M)"),
        pseudocode="Build failure function then linear scan.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="pass", iteration=0)


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.STRING_MATCH,
        title="String Match",
        description="First occurrence.",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="abracadabra\nabra", expected_output="1"),
            SampleTestCase(input_text="hello\nworld", expected_output="-1"),
            SampleTestCase(input_text="abcabcabc\ncab", expected_output="3"),
        ],
    )


def test_passes_with_correct_indices() -> None:
    v = StringMatchVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1", "-1", "3"],
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert StringMatchVerifier.target_algorithm is TargetAlgorithm.STRING_MATCH


def test_catches_non_integer_output() -> None:
    v = StringMatchVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["one", "-1", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "output_is_single_int"


def test_catches_out_of_range_index() -> None:
    v = StringMatchVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["100", "-1", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "index_valid_range"


def test_catches_zero_index() -> None:
    v = StringMatchVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["0", "-1", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "index_valid_range"


def test_catches_wrong_index_text_window_mismatch() -> None:
    v = StringMatchVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["2", "-1", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "text_at_index_matches_pattern"


def test_catches_false_negative() -> None:
    v = StringMatchVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["-1", "-1", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "existence_consistent"


def test_catches_false_positive_when_no_match() -> None:
    v = StringMatchVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["1", "1", "3"],
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "text_at_index_matches_pattern"


def test_pattern_at_end_of_text() -> None:
    v = StringMatchVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.STRING_MATCH,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="abcdef\ndef", expected_output="4"),
            SampleTestCase(input_text="abcdef\nef", expected_output="5"),
            SampleTestCase(input_text="abcdef\nf", expected_output="6"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["4", "5", "6"])
    assert violations == []


def test_pattern_equals_text() -> None:
    v = StringMatchVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.STRING_MATCH,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="abc\nabc", expected_output="1"),
            SampleTestCase(input_text="x\nx", expected_output="1"),
            SampleTestCase(input_text="hi\nhi", expected_output="1"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["1", "1", "1"])
    assert violations == []


def test_pattern_longer_than_text_no_match() -> None:
    v = StringMatchVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.STRING_MATCH,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="ab\nabcde", expected_output="-1"),
            SampleTestCase(input_text="ab\nabcde", expected_output="-1"),
            SampleTestCase(input_text="ab\nabcde", expected_output="-1"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["-1"] * 3)
    assert violations == []


def test_input_with_whitespace_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.STRING_MATCH,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="hello world\npattern", expected_output="x"),
            SampleTestCase(input_text="abc\nb", expected_output="2"),
            SampleTestCase(input_text="abc\nb", expected_output="2"),
        ],
    )
    v = StringMatchVerifier()
    assert v.count_engaged_samples(spec) == 2


def test_count_engaged_all_parseable() -> None:
    assert StringMatchVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_count_engaged_partial() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.STRING_MATCH,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="only one line", expected_output="x"),
            SampleTestCase(input_text="abc\nb", expected_output="2"),
            SampleTestCase(input_text="too\nmany\nlines", expected_output="x"),
        ],
    )
    assert StringMatchVerifier().count_engaged_samples(spec) == 1


def test_get_verifier_returns_stringmatch_after_module_import() -> None:
    register_verifier(StringMatchVerifier())
    verifier = get_verifier(TargetAlgorithm.STRING_MATCH)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.STRING_MATCH


def test_overlapping_pattern() -> None:
    """aaaa + aa → first occurrence = 1."""
    v = StringMatchVerifier()
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.STRING_MATCH,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="aaaa\naa", expected_output="1"),
            SampleTestCase(input_text="aaaa\naa", expected_output="1"),
            SampleTestCase(input_text="aaaa\naa", expected_output="1"),
        ],
    )
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["1"] * 3)
    assert violations == []
