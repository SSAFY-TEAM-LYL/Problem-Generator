"""Test-suite 생성 아티팩트 단위 테스트 (Phase 3 M4 step1).

GeneratorContract(frozen 입력 생성기 계약) + ScaleFamily/EdgeCaseSpec +
GeneratedTestCase(expected 후행) + TestSuite(assembled 풀셋). frozen + extra=forbid +
기본값 + 검증 규칙 + computed property.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ipe.v1.schema import (
    ConstraintRange,
    EdgeCaseSpec,
    GeneratedTestCase,
    GeneratorContract,
    ResolvedEdgeCase,
    ScaleFamily,
    TestSuite,
)


def _contract() -> GeneratorContract:
    return GeneratorContract(
        scale_families=(
            ScaleFamily(
                name="small",
                case_count=3,
                field_bounds=(ConstraintRange(name="N", min_value=1, max_value=10),),
            ),
            ScaleFamily(
                name="large",
                case_count=2,
                field_bounds=(
                    ConstraintRange(name="N", min_value=10000, max_value=100000),
                ),
            ),
        ),
        edge_cases=(
            EdgeCaseSpec(name="single", description="N=1"),
            EdgeCaseSpec(name="max_size", description="상한"),
        ),
    )


# ---------- ScaleFamily ----------


def test_scale_family_minimal_and_defaults() -> None:
    f = ScaleFamily(name="small", case_count=5)
    assert f.name == "small"
    assert f.case_count == 5
    assert f.field_bounds == ()  # default
    assert f.description == ""


def test_scale_family_rejects_nonpositive_case_count() -> None:
    with pytest.raises(ValidationError):
        ScaleFamily(name="small", case_count=0)  # gt=0


def test_scale_family_requires_name() -> None:
    with pytest.raises(ValidationError):
        ScaleFamily(name="", case_count=1)  # min_length=1


def test_scale_family_is_frozen_and_forbids_extra() -> None:
    f = ScaleFamily(name="small", case_count=1)
    with pytest.raises(ValidationError):
        f.case_count = 2  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ScaleFamily(name="s", case_count=1, unexpected="nope")  # type: ignore[call-arg]


# ---------- EdgeCaseSpec ----------


def test_edge_case_spec_minimal_and_defaults() -> None:
    e = EdgeCaseSpec(name="empty")
    assert e.name == "empty"
    assert e.description == ""


def test_edge_case_spec_requires_name() -> None:
    with pytest.raises(ValidationError):
        EdgeCaseSpec(name="")  # min_length=1


# ---------- GeneratorContract ----------


def test_generator_contract_construction_and_defaults() -> None:
    c = _contract()
    assert len(c.scale_families) == 2
    assert len(c.edge_cases) == 2
    assert c.determinism_seed is None  # default
    assert c.notes == ""


def test_generator_contract_requires_at_least_one_scale_family() -> None:
    with pytest.raises(ValidationError):
        GeneratorContract(scale_families=())  # min_length=1


def test_generator_contract_total_planned_cases() -> None:
    c = _contract()
    # scale: 3 + 2 = 5, edge: 2 → 7
    assert c.total_planned_cases == 7


def test_generator_contract_edge_cases_default_empty() -> None:
    c = GeneratorContract(
        scale_families=(ScaleFamily(name="small", case_count=4),),
    )
    assert c.edge_cases == ()
    assert c.total_planned_cases == 4


def test_generator_contract_is_frozen_and_forbids_extra() -> None:
    c = _contract()
    with pytest.raises(ValidationError):
        c.notes = "x"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        GeneratorContract(
            scale_families=(ScaleFamily(name="s", case_count=1),),
            unexpected="nope",  # type: ignore[call-arg]
        )


# ---------- GeneratedTestCase ----------


def test_generated_case_expected_pending_by_default() -> None:
    # bootstrap(§7): 입력 먼저, expected 는 golden 실행 후 채움
    case = GeneratedTestCase(input_text="3\n1 2 3", category="small")
    assert case.expected_output is None  # pending
    assert case.category == "small"


def test_generated_case_filled_expected() -> None:
    case = GeneratedTestCase(
        input_text="3\n1 2 3", category="small", expected_output="6"
    )
    assert case.expected_output == "6"


def test_generated_case_requires_category() -> None:
    with pytest.raises(ValidationError):
        GeneratedTestCase(input_text="x", category="")  # min_length=1


def test_generated_case_is_frozen_and_forbids_extra() -> None:
    case = GeneratedTestCase(input_text="x", category="small")
    with pytest.raises(ValidationError):
        case.expected_output = "1"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        GeneratedTestCase(
            input_text="x", category="s", unexpected="nope"  # type: ignore[call-arg]
        )


# ---------- ResolvedEdgeCase (Phase 5a — 엣지 의미 golden-defined) ----------


def test_resolved_edge_case_pending_by_default() -> None:
    # 부트스트랩: 입력은 IR 파생, expected 는 golden 실행 후 채움 (GeneratedTestCase 동형)
    edge = ResolvedEdgeCase(
        name="unreachable", input_text="2 0\n1\n2", rationale="분리 그래프"
    )
    assert edge.name == "unreachable"
    assert edge.expected_output is None  # pending
    assert edge.rationale == "분리 그래프"


def test_resolved_edge_case_filled_expected() -> None:
    edge = ResolvedEdgeCase(
        name="min", input_text="1 0\n1\n1", expected_output="0"
    )
    assert edge.expected_output == "0"
    assert edge.rationale == ""  # default


def test_resolved_edge_case_requires_name_and_input() -> None:
    with pytest.raises(ValidationError):
        ResolvedEdgeCase(name="", input_text="x")  # name min_length=1
    with pytest.raises(ValidationError):
        ResolvedEdgeCase(name="min", input_text="")  # input_text min_length=1


def test_resolved_edge_case_is_frozen_and_forbids_extra() -> None:
    edge = ResolvedEdgeCase(name="min", input_text="x")
    with pytest.raises(ValidationError):
        edge.expected_output = "1"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ResolvedEdgeCase(
            name="min", input_text="x", unexpected="nope"  # type: ignore[call-arg]
        )


# ---------- TestSuite ----------


def test_test_suite_assembled_when_all_expected_filled() -> None:
    suite = TestSuite(
        cases=(
            GeneratedTestCase(input_text="a", category="small", expected_output="1"),
            GeneratedTestCase(input_text="b", category="large", expected_output="2"),
        ),
        golden_origin="opus",
    )
    assert suite.is_assembled is True
    assert suite.golden_origin == "opus"


def test_test_suite_not_assembled_when_any_pending() -> None:
    suite = TestSuite(
        cases=(
            GeneratedTestCase(input_text="a", category="small", expected_output="1"),
            GeneratedTestCase(input_text="b", category="edge"),  # pending
        ),
    )
    assert suite.is_assembled is False
    assert suite.golden_origin is None  # default


def test_test_suite_requires_at_least_one_case() -> None:
    with pytest.raises(ValidationError):
        TestSuite(cases=())  # min_length=1


def test_test_suite_is_frozen_and_forbids_extra() -> None:
    suite = TestSuite(
        cases=(GeneratedTestCase(input_text="a", category="s", expected_output="1"),)
    )
    with pytest.raises(ValidationError):
        suite.golden_origin = "x"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        TestSuite(
            cases=(GeneratedTestCase(input_text="a", category="s"),),
            unexpected="nope",  # type: ignore[call-arg]
        )
