"""ProblemSpec + 부속 모델 단위 테스트 (D안 PR-A1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import (
    ConstraintRange,
    IOContract,
    ProblemSpec,
    SampleTestCase,
)


def _valid_io_contract() -> IOContract:
    return IOContract(
        input_format="V E s t followed by E lines of (u v w)",
        output_format="single integer: shortest distance, or -1 if unreachable",
    )


def _valid_samples() -> list[SampleTestCase]:
    return [
        SampleTestCase(input_text="2 1 0 1\n0 1 5", expected_output="5"),
        SampleTestCase(input_text="3 2 0 2\n0 1 1\n1 2 2", expected_output="3"),
        SampleTestCase(input_text="2 0 0 1", expected_output="-1"),
    ]


def _valid_spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm="Dijkstra",
        title="Shortest path on weighted DAG",
        description="Given V vertices and E edges, find shortest path from s to t.",
        constraints=[
            ConstraintRange(name="V", min_value=2, max_value=1000),
            ConstraintRange(name="E", min_value=1, max_value=10000),
        ],
        io_contract=_valid_io_contract(),
        sample_testcases=_valid_samples(),
    )


def test_problem_spec_constructs_with_minimal_valid_input() -> None:
    spec = _valid_spec()
    assert spec.target_algorithm == "Dijkstra"
    assert len(spec.sample_testcases) == 3
    assert spec.time_limit_ms == 2000
    assert spec.memory_limit_mb == 256


def test_problem_spec_is_frozen_immutable() -> None:
    spec = _valid_spec()
    with pytest.raises(ValidationError):
        spec.title = "mutated"


def test_problem_spec_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ProblemSpec.model_validate(
            {
                "target_algorithm": "X",
                "title": "t",
                "description": "d",
                "io_contract": _valid_io_contract().model_dump(),
                "sample_testcases": [s.model_dump() for s in _valid_samples()],
                "unknown_field": "x",
            }
        )


def test_problem_spec_requires_3_to_5_samples_min() -> None:
    base = _valid_spec().model_dump()
    base["sample_testcases"] = base["sample_testcases"][:2]
    with pytest.raises(ValidationError):
        ProblemSpec.model_validate(base)


def test_problem_spec_requires_3_to_5_samples_max() -> None:
    base = _valid_spec().model_dump()
    extra_sample = SampleTestCase(input_text="x", expected_output="y").model_dump()
    base["sample_testcases"] = [
        *base["sample_testcases"],
        extra_sample,
        extra_sample,
        extra_sample,
    ]
    with pytest.raises(ValidationError):
        ProblemSpec.model_validate(base)


def test_constraint_range_rejects_inverted_bounds() -> None:
    with pytest.raises(ValidationError):
        ConstraintRange(name="N", min_value=10, max_value=5)


def test_constraint_range_allows_equal_bounds() -> None:
    cr = ConstraintRange(name="K", min_value=7, max_value=7)
    assert cr.min_value == cr.max_value == 7


def test_io_contract_default_separator_is_newline() -> None:
    contract = _valid_io_contract()
    assert contract.example_separator == "newline"


def test_problem_spec_requires_positive_time_limit() -> None:
    base = _valid_spec().model_dump()
    base["time_limit_ms"] = 0
    with pytest.raises(ValidationError):
        ProblemSpec.model_validate(base)


def test_problem_spec_requires_non_empty_target_algorithm() -> None:
    base = _valid_spec().model_dump()
    base["target_algorithm"] = ""
    with pytest.raises(ValidationError):
        ProblemSpec.model_validate(base)
