"""v2 CLI(main_v2) 단위 테스트 (Phase 3 M3 follow-up).

mock LLM 으로 build_v2_graph 한 그래프를 main(graph=...) 에 주입 → 실 LLM/네트워크
없이 CLI plumbing(arg parse / summary / exit code) 결정론 검증.
"""

from __future__ import annotations

from typing import Any

import pytest

from ipe.v1.schema import (
    BlueprintFormalization,
    IOFieldSpec,
    IOSchema,
    NarrativeDraft,
    NarrativeFaithfulnessReport,
    StrategySeed,
    TargetAlgorithm,
)
from ipe.v2.graph import build_v2_graph
from ipe.v2.main_v2 import main


class _FixedStrategistLLM:
    def seed(self, state: Any) -> StrategySeed:
        return StrategySeed(reduction_core=TargetAlgorithm.DIJKSTRA, domain="logistics")


class _FixedFormalizerLLM:
    def formalize(self, state: Any) -> BlueprintFormalization:
        return BlueprintFormalization(
            io_schema=IOSchema(
                inputs=(IOFieldSpec(name="N", type="int"),),
                output_type="int",
                output_format="단일 정수",
            )
        )


class _FixedNarrativeLLM:
    def render(self, state: Any, *, hidden: bool) -> NarrativeDraft:
        return NarrativeDraft(scenario="물류 시나리오 지문")


class _ScriptedFaithfulnessLLM:
    def __init__(self, faithful_seq: list[bool]) -> None:
        self._seq = list(faithful_seq)
        self.calls = 0

    def assess(self, state: Any) -> NarrativeFaithfulnessReport:
        val = self._seq[min(self.calls, len(self._seq) - 1)]
        self.calls += 1
        return NarrativeFaithfulnessReport(
            faithful=val, distortions=() if val else ("왜곡 근거",)
        )


def _mock_graph(*, faithful_seq: list[bool], hidden: bool = True) -> Any:
    return build_v2_graph(
        strategist_llm=_FixedStrategistLLM(),
        formalizer_llm=_FixedFormalizerLLM(),
        narrative_llm=_FixedNarrativeLLM(),
        faithfulness_llm=_ScriptedFaithfulnessLLM(faithful_seq),
        hidden=hidden,
    )


def test_main_success_returns_zero_and_prints_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(
        ["--algorithm", "dijkstra"], graph=_mock_graph(faithful_seq=[True])
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "final_status=success" in out
    assert "reduction_core=dijkstra" in out
    assert "faithful=True" in out


def test_main_failure_returns_one(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["--algorithm", "dijkstra", "--max-iter", "2"],
        graph=_mock_graph(faithful_seq=[False]),
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "final_status=fail_faithfulness" in out


def test_main_verbose_prints_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    main(
        ["--algorithm", "dijkstra", "--verbose"],
        graph=_mock_graph(faithful_seq=[True]),
    )
    out = capsys.readouterr().out
    assert "VERBOSE" in out
    assert "물류 시나리오 지문" in out


def test_main_direct_flag_accepted(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["--algorithm", "dijkstra", "--direct"],
        graph=_mock_graph(faithful_seq=[True]),
    )
    assert code == 0
    assert "hidden=False" in capsys.readouterr().out


def test_main_unsupported_algorithm_exits() -> None:
    with pytest.raises(SystemExit):
        main(["--algorithm", "no_such_algo"], graph=_mock_graph(faithful_seq=[True]))
