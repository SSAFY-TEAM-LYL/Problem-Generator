"""LISVerifier 단위 테스트 (D안 Phase 2a PR-B1)."""

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
from ipe.v1.verifiers import LISVerifier, get_verifier, register_verifier


def _io() -> IOContract:
    return IOContract(
        input_format="N then N integers",
        output_format="single integer (LIS length, strictly increasing)",
    )


def _spec_three_samples() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.LIS,
        title="Longest strictly increasing subsequence length",
        description=(
            "Given N integers, output the length of the longest strictly "
            "increasing subsequence."
        ),
        io_contract=_io(),
        sample_testcases=[
            # arr = [1, 3, 2, 4] → LIS = [1,3,4] or [1,2,4] → length 3
            SampleTestCase(input_text="4\n1 3 2 4", expected_output="3"),
            # arr = [5, 4, 3, 2, 1] → LIS = any single → length 1
            SampleTestCase(input_text="5\n5 4 3 2 1", expected_output="1"),
            # arr = [10, 20, 30] strictly increasing → length 3
            SampleTestCase(input_text="3\n10 20 30", expected_output="3"),
        ],
    )


def _design() -> AlgorithmDesign:
    return AlgorithmDesign(
        algorithm_name="LIS",
        complexity_target=ComplexityBound(time_big_o="O(N log N)", space_big_o="O(N)"),
        pseudocode="patience sort with bisect_left.",
    )


def _attempt() -> SolutionAttempt:
    return SolutionAttempt(code="print(0)", iteration=0)


# ---------- Pass paths ----------


def test_passes_with_golden_outputs() -> None:
    v = LISVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["3", "1", "3"]
    )
    assert violations == []


def test_target_algorithm_constant() -> None:
    assert LISVerifier.target_algorithm is TargetAlgorithm.LIS
    assert LISVerifier().target_algorithm is TargetAlgorithm.LIS


# ---------- Invariant 1: non_negative_length ----------


def test_catches_negative_length() -> None:
    v = LISVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["-1", "1", "3"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "non_negative_length"
    assert violations[0].evidence["actual_output"] == "-1"


# ---------- Invariant 2: length_le_input_size ----------


def test_catches_length_exceeds_n() -> None:
    """sample 1 의 N=5 인데 output 10 → length > N violation."""
    v = LISVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["3", "10", "3"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "length_le_input_size"
    assert violations[0].evidence["N"] == "5"
    assert violations[0].evidence["actual_output"] == "10"


# ---------- Invariant 3: length_optimal (patience sort golden) ----------


def test_catches_suboptimal_length() -> None:
    """sample 0 의 golden=3 인데 LLM 이 2 라 했음 (suboptimal)."""
    v = LISVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["2", "1", "3"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "length_optimal"
    assert violations[0].evidence["patience_sort_golden"] == "3"


def test_catches_overclaimed_length_within_n_bound() -> None:
    """sample 1 의 N=5, golden=1 인데 LLM 이 4 (≤ N 이지만 golden 보다 큼)."""
    v = LISVerifier()
    violations = v.verify(
        _spec_three_samples(), _design(), _attempt(), sample_outputs=["3", "4", "3"]
    )
    assert len(violations) == 1
    assert violations[0].invariant_kind == "length_optimal"
    assert violations[0].evidence["patience_sort_golden"] == "1"


# ---------- Edge cases ----------


def test_empty_sequence_lis_zero() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.LIS,
        title="empty",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="0", expected_output="0"),
            SampleTestCase(input_text="1\n42", expected_output="1"),
            SampleTestCase(input_text="3\n7 7 7", expected_output="1"),
        ],
    )
    v = LISVerifier()
    # strictly increasing 에서 [7,7,7] 은 LIS=1 (단일 원소).
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["0", "1", "1"])
    assert violations == []


def test_strictly_increasing_rejects_non_decreasing_overclaim() -> None:
    """[7,7,7] 은 strict LIS=1. LLM 이 non-decreasing 으로 3 claim 하면 reject."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.LIS,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="3\n7 7 7", expected_output="1"),
            SampleTestCase(input_text="3\n1 2 3", expected_output="3"),
            SampleTestCase(input_text="3\n3 1 2", expected_output="2"),
        ],
    )
    v = LISVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["3", "3", "2"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "length_optimal"


# ---------- Parse skip ----------


def test_unparseable_input_silent_skip() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.LIS,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="4\n1 3 2 4", expected_output="3"),
            SampleTestCase(input_text="3\n1 2 3", expected_output="3"),
        ],
    )
    v = LISVerifier()
    # sample 0 parse fail → skip. sample 1 actual=99 → length_le_input_size
    # violation (N=4, 99>4). sample 2 actual=3 → pass.
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["any", "99", "3"])
    assert len(violations) == 1
    assert violations[0].invariant_kind == "length_le_input_size"


def test_unparseable_output_silent_skip() -> None:
    v = LISVerifier()
    violations = v.verify(
        _spec_three_samples(),
        _design(),
        _attempt(),
        sample_outputs=["not-a-number", "1", "3"],
    )
    assert violations == []


def test_n_mismatch_with_actual_count_silent_skip() -> None:
    """N=5 명시했는데 실제 4개 → parse fail → skip."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.LIS,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="5\n1 2 3 4", expected_output="x"),
            SampleTestCase(input_text="3\n1 2 3", expected_output="3"),
            SampleTestCase(input_text="3\n1 2 3", expected_output="3"),
        ],
    )
    v = LISVerifier()
    violations = v.verify(spec, _design(), _attempt(), sample_outputs=["1", "3", "3"])
    assert violations == []


# ---------- count_engaged_samples ----------


def test_count_engaged_all_parseable() -> None:
    assert LISVerifier().count_engaged_samples(_spec_three_samples()) == 3


def test_count_engaged_partial() -> None:
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.LIS,
        title="t",
        description="d",
        io_contract=_io(),
        sample_testcases=[
            SampleTestCase(input_text="garbage", expected_output="x"),
            SampleTestCase(input_text="3\n1 2 3", expected_output="3"),
            SampleTestCase(input_text="bad N", expected_output="x"),
        ],
    )
    assert LISVerifier().count_engaged_samples(spec) == 1


# ---------- Dispatch registry ----------


def test_get_verifier_returns_lis_after_module_import() -> None:
    # test_dijkstra.py 가 clear_registry 호출했을 수 있어 self-sufficient register.
    register_verifier(LISVerifier())
    verifier = get_verifier(TargetAlgorithm.LIS)
    assert verifier is not None
    assert verifier.target_algorithm is TargetAlgorithm.LIS
