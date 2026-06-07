"""Faithfulness 노드 단위 테스트 (Phase 3 M3 step4, round-trip).

- ``make_faithfulness_node``: narrative + blueprint → NarrativeFaithfulnessReport
  (state.faithfulness). 정보 은닉=OK(faithful), 정보 왜곡=reject(faithful=False).
- precondition: narrative + blueprint 둘 다 필요.

mock LLM 으로 sandbox/네트워크 없이 결정론 검증.
"""

from __future__ import annotations

import pytest

from ipe.v1.schema import (
    IOFieldSpec,
    IOSchema,
    Narrative,
    NarrativeFaithfulnessReport,
    OutputInvariant,
    ProblemBlueprint,
    TargetAlgorithm,
)
from ipe.v2.nodes import make_faithfulness_node
from ipe.v2.state import V2State, initial_v2_state


def _blueprint() -> ProblemBlueprint:
    return ProblemBlueprint(
        reduction_core=TargetAlgorithm.DIJKSTRA,
        domain="logistics",
        io_schema=IOSchema(
            inputs=(IOFieldSpec(name="N", type="int"),),
            output_type="int",
            output_format="단일 정수 (최단거리)",
        ),
        output_invariants=(
            OutputInvariant(kind="non_negative", description="거리는 음수 불가"),
        ),
    )


def _narrative(hidden: bool = True) -> Narrative:
    return Narrative(
        scenario="물류 센터에서 거점 간 최소 이동 비용을 구하라 ...",
        hidden=hidden,
        domain="logistics",
    )


def _state(*, with_narrative: bool = True, with_blueprint: bool = True) -> V2State:
    base = initial_v2_state("run-v2", TargetAlgorithm.DIJKSTRA)
    update: dict[str, object] = {}
    if with_blueprint:
        update["blueprint"] = _blueprint()
    if with_narrative:
        update["narrative"] = _narrative()
    return base.model_copy(update=update)


class _FixedFaithfulnessLLM:
    """고정 report 를 반환하는 mock (state 무시)."""

    def __init__(self, report: NarrativeFaithfulnessReport) -> None:
        self._report = report

    def assess(self, state: V2State) -> NarrativeFaithfulnessReport:
        return self._report


def test_faithfulness_populates_report_when_faithful() -> None:
    report = NarrativeFaithfulnessReport(faithful=True)
    out = make_faithfulness_node(_FixedFaithfulnessLLM(report))(_state())

    assert out.faithfulness is not None
    assert out.faithfulness.faithful is True
    assert out.faithfulness.distortions == ()


def test_faithfulness_records_distortions_when_unfaithful() -> None:
    report = NarrativeFaithfulnessReport(
        faithful=False,
        distortions=("지문은 '최댓값'을 요구하나 schema 출력은 최단거리",),
    )
    out = make_faithfulness_node(_FixedFaithfulnessLLM(report))(_state())

    assert out.faithfulness is not None
    assert out.faithfulness.faithful is False
    assert len(out.faithfulness.distortions) == 1


def test_faithfulness_requires_narrative() -> None:
    bare = _state(with_narrative=False)  # blueprint 만 있음
    node = make_faithfulness_node(
        _FixedFaithfulnessLLM(NarrativeFaithfulnessReport(faithful=True))
    )
    with pytest.raises(ValueError, match="narrative"):
        node(bare)


def test_faithfulness_requires_blueprint() -> None:
    bare = _state(with_blueprint=False)  # narrative 만 있음
    node = make_faithfulness_node(
        _FixedFaithfulnessLLM(NarrativeFaithfulnessReport(faithful=True))
    )
    with pytest.raises(ValueError, match="blueprint"):
        node(bare)


def test_faithfulness_preserves_original_state() -> None:
    state = _state()
    out = make_faithfulness_node(
        _FixedFaithfulnessLLM(NarrativeFaithfulnessReport(faithful=True))
    )(state)
    assert state.faithfulness is None  # 원본 불변
    assert out.faithfulness is not None
    assert out.narrative is state.narrative  # narrative/blueprint 보존
    assert out.blueprint is state.blueprint
