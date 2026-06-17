"""채점셋 확장 — LLM 다양 입력 + golden oracle assemble 의 순수 로직 테스트.

LLM/sandbox 는 mock. ``expand_grading_suite`` (samples + 생성 입력 → golden 실행으로
expected 채움, 파싱 못하는 입력 drop, samples 최소 생존)의 결정론 로직만 검증한다.
실 LLM(다양 입력 생성) + 실 sandbox 는 hybrid CLI 실행으로 입증.
"""

from __future__ import annotations

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import (
    GeneratedTestCase,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    TargetAlgorithm,
)
from ipe.v2.grading_expand import expand_grading_suite


def _spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="두 수 합",
        description="합이 target 인 서로 다른 두 수의 쌍 개수를 센다.",
        io_contract=IOContract(input_format="N\na_1..a_N\nT", output_format="개수"),
        sample_testcases=[
            SampleTestCase(input_text="3\n1 2 3\n5", expected_output="1"),
            SampleTestCase(input_text="2\n1 1\n2", expected_output="1"),
            SampleTestCase(input_text="1\n5\n5", expected_output="0"),
        ],
    )


class _StubGenerator:
    """고정 입력 emit (expected=None pending) — 결정론 mock."""

    def __init__(self, cases: tuple[GeneratedTestCase, ...]) -> None:
        self._cases = cases

    def generate(
        self, spec: ProblemSpec, *, target_count: int
    ) -> tuple[GeneratedTestCase, ...]:
        return self._cases


class _GoldenRunner:
    """golden mock — stdin 에 'BAD' 포함이면 파싱실패(RTE) 모사, 나머지 OK."""

    def run(self, spec: RunSpec) -> RunResult:
        if "BAD" in spec.stdin:
            return RunResult(
                status="RTE", returncode=1, stdout="", stderr="parse error", elapsed_ms=2
            )
        return RunResult(
            status="OK", returncode=0, stdout="result\n", stderr="", elapsed_ms=7
        )


def test_expand_combines_samples_and_generated() -> None:
    """samples + 생성 입력 모두 golden 으로 assemble → 풀 채점셋 (expected 채워짐)."""
    gen = _StubGenerator(
        (
            GeneratedTestCase(input_text="5\n1 2 3 4 5\n6", category="large"),
            GeneratedTestCase(input_text="1\n0\n0", category="edge_single"),
        )
    )
    suite = expand_grading_suite(
        _spec(), "# golden", generator=gen, runner=_GoldenRunner(), golden_origin="opus"
    )
    assert len(suite.cases) == 5  # 3 samples + 2 generated
    assert suite.is_assembled  # 모든 expected 채워짐 (출하가능)
    assert suite.golden_origin == "opus"
    categories = [c.category for c in suite.cases]
    assert categories.count("sample") == 3
    assert "large" in categories and "edge_single" in categories
    # golden_elapsed_ms 채워짐 — 백엔드 TL 산정 근거 (계약 v1.0)
    assert all(c.golden_elapsed_ms is not None for c in suite.cases)


def test_expand_drops_inputs_golden_cannot_parse() -> None:
    """golden 이 못 푸는(형식 불일치) 생성 입력은 drop, samples 는 보존."""
    gen = _StubGenerator(
        (
            GeneratedTestCase(input_text="BAD malformed input", category="large"),
            GeneratedTestCase(input_text="4\n1 2 3 4\n5", category="medium"),
        )
    )
    suite = expand_grading_suite(
        _spec(), "# golden", generator=gen, runner=_GoldenRunner()
    )
    categories = [c.category for c in suite.cases]
    assert "large" not in categories  # 파싱 실패 입력 drop
    assert "medium" in categories
    assert categories.count("sample") == 3  # samples 최소 생존
    assert len(suite.cases) == 4


def test_expand_falls_back_to_samples_when_generator_empty() -> None:
    """생성 0개여도 samples 가 golden 으로 assemble — 최소 채점셋 보장 (전부-drop 방지)."""
    suite = expand_grading_suite(
        _spec(), "# golden", generator=_StubGenerator(()), runner=_GoldenRunner()
    )
    assert len(suite.cases) == 3  # samples only
    assert all(c.category == "sample" for c in suite.cases)
    assert suite.is_assembled


def test_expand_passes_target_count_to_generator() -> None:
    """target_count 가 생성기로 전달된다 (호출 인자 검증)."""
    seen: dict[str, int] = {}

    class _RecordingGen:
        def generate(
            self, spec: ProblemSpec, *, target_count: int
        ) -> tuple[GeneratedTestCase, ...]:
            seen["target_count"] = target_count
            return ()

    expand_grading_suite(
        _spec(),
        "# golden",
        generator=_RecordingGen(),
        runner=_GoldenRunner(),
        target_count=30,
    )
    assert seen["target_count"] == 30
