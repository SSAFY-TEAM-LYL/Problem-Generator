"""v2 test-suite 통합테스트 — with_test_suite=True (Phase 3 M4 step5).

verification 통과 후 generator_designer → input_generator → suite_assembler 가
풀 채점셋을 만들어 end_success 로 종료하는 배선을 mock LLM + scripted runner 로 검증:
1. success: 검증 통과 → contract 저작 → 결정론 입력 생성 → golden 으로 expected 채움.
2. verification fail: suite 노드 미진입 (test_suite/generator_contract None).
3. partial drop: golden 이 일부 입력 실행 실패 → 그 케이스만 drop, 나머지로 assembled
   (assembled/planned 비율 = 규약 정합 anchor 의 분자/분모 보존 확인).
4. build guard: synthesis 항상 배선(Phase 4) — with_test_suite 만으로도 golden 필수.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ipe.sandbox.runner import RunResult, RunSpec
from ipe.v1.schema import (
    AlgorithmDesign,
    BlueprintFormalization,
    ComplexityBound,
    ConstraintRange,
    GraphShape,
    Invariant,
    InvariantViolation,
    IOFieldSpec,
    IOSchema,
    NarrativeDraft,
    NarrativeFaithfulnessReport,
    SolutionAttempt,
    StrategySeed,
    TargetAlgorithm,
)
from ipe.v2.graph import build_v2_graph
from ipe.v2.state import V2State, initial_v2_state

# ---------- modeling mocks ----------


class _FixedStrategistLLM:
    def seed(self, state: Any) -> StrategySeed:
        return StrategySeed(reduction_core=TargetAlgorithm.SORT, domain="logistics")


class _FixedFormalizerLLM:
    def formalize(self, state: Any) -> BlueprintFormalization:
        # weighted_edges schema — 순수 투영(Phase 3)이 small/large tier + 실현가능
        # edge(min_size/max_size/empty/disconnected)를 결정론 파생. V_min=3 이라 'empty'
        # edge 는 항상 '3 0'(정점 3·간선 0)이고, 연결 그래프(small/large/min/max/
        # disconnected)는 V>=3 → 간선 >=2 이라 '3 0' 과 절대 충돌 안 함 → partial-drop
        # 이 'empty' 케이스만 결정론적으로 떨굴 수 있다.
        return BlueprintFormalization(
            io_schema=IOSchema(
                inputs=(
                    IOFieldSpec(
                        name="edges",
                        type="weighted_edges",
                        size_range=ConstraintRange(name="V", min_value=3, max_value=8),
                        value_range=ConstraintRange(name="w", min_value=1, max_value=9),
                    ),
                ),
                output_type="int",
                output_format="단일 정수",
            )
        )


class _ShapedFormalizerLLM:
    """graph_shape 핀된 weighted_edges — GraphBackbone 이 owns → Phase 5a 퇴화 엣지 파생.

    `_FixedFormalizerLLM` 과 동일하되 graph_shape(maybe_disconnected) 를 핀해 reconciler 가
    min/unreachable 퇴화 입력을 differential 에 더하고 edge_filler 가 채우게 한다.
    """

    def formalize(self, state: Any) -> BlueprintFormalization:
        return BlueprintFormalization(
            io_schema=IOSchema(
                inputs=(
                    IOFieldSpec(
                        name="edges",
                        type="weighted_edges",
                        size_range=ConstraintRange(name="V", min_value=3, max_value=8),
                        value_range=ConstraintRange(name="w", min_value=1, max_value=9),
                        graph_shape=GraphShape(
                            directed=False, connectivity="maybe_disconnected"
                        ),
                    ),
                ),
                output_type="int",
                output_format="단일 정수",
            )
        )


class _FixedNarrativeLLM:
    def render(self, state: Any, *, hidden: bool) -> NarrativeDraft:
        return NarrativeDraft(title="물류 경로", scenario="물류 시나리오")


class _FaithfulLLM:
    def assess(self, state: Any) -> NarrativeFaithfulnessReport:
        return NarrativeFaithfulnessReport(faithful=True)


# ---------- synthesis mocks ----------


class _DesignerLLM:
    def generate(self, state: Any) -> AlgorithmDesign:
        return AlgorithmDesign(
            algorithm_name="sort",
            complexity_target=ComplexityBound(
                time_big_o="O(N log N)", space_big_o="O(N)"
            ),
            pseudocode="sort values.",
            invariants=[Invariant(kind="sorted", description="x")],
        )


class _CoderLLM:
    def __init__(self, code: str) -> None:
        self._code = code

    def generate(self, state: Any) -> SolutionAttempt:
        return SolutionAttempt(code=self._code, iteration=0)


# ---------- scripted runner ----------


class _MarkerRunner:
    def __init__(self, fn: Callable[[str, str], tuple[str, str]]) -> None:
        self._fn = fn

    def run(self, spec: RunSpec) -> RunResult:
        py = sorted(Path(spec.cwd).glob("*.py"))
        code = py[0].read_text(encoding="utf-8") if py else ""
        status, stdout = self._fn(code, spec.stdin)
        return RunResult(
            status=status,  # type: ignore[arg-type]
            returncode=0 if status == "OK" else 1,
            stdout=stdout,
            stderr="" if status == "OK" else "boom",
            elapsed_ms=1,
        )


def _echo_answer(code: str, stdin: str) -> tuple[str, str]:
    return ("OK", f"ans-{stdin}")


def _fail_on_empty_graph(code: str, stdin: str) -> tuple[str, str]:
    """'empty' edge('3 0' — 정점 3·간선 0)만 실행 실패. 연결 그래프(V>=3 → 간선 >=2)는
    이 패턴과 절대 충돌 안 함 → 그 케이스만 결정론적으로 drop. synthesis sample 도 무관."""
    if stdin.strip() == "3 0":
        return ("RTE", "")
    return _echo_answer(code, stdin)


def _final(raw: Any) -> V2State:
    return raw if isinstance(raw, V2State) else V2State.model_validate(raw)


def _suite_graph(
    *,
    runner_fn: Callable[[str, str], tuple[str, str]] = _echo_answer,
    verifier_getter: Any = None,
    formalizer_llm: Any = None,
) -> Any:
    return build_v2_graph(
        composition_mode="single",  # 단일-알고리즘 flow 테스트 → validator p1
        strategist_llm=_FixedStrategistLLM(),
        formalizer_llm=formalizer_llm
        if formalizer_llm is not None
        else _FixedFormalizerLLM(),
        narrative_llm=_FixedNarrativeLLM(),
        faithfulness_llm=_FaithfulLLM(),
        designer_llm=_DesignerLLM(),
        golden_llms=[_CoderLLM("# G0"), _CoderLLM("# G1")],
        brute_llm=_CoderLLM("# B"),
        golden_origins=["opus", "sonnet"],
        runner=_MarkerRunner(runner_fn),
        verifier_getter=(
            verifier_getter if verifier_getter is not None else (lambda _a: None)
        ),
        with_test_suite=True,
    )


class _ViolatingVerifier:
    """symbolic verifier mock — invariant violation 검출 (verification fail 유발)."""

    def verify(self, **_kw: Any) -> list[InvariantViolation]:
        return [
            InvariantViolation(invariant_kind="non_negative", description="음수 거리")
        ]

    def count_engaged_samples(self, spec: Any) -> int:
        return len(spec.sample_testcases)


def _run(graph: Any, run_id: str) -> V2State:
    return _final(
        graph.invoke(
            initial_v2_state(run_id, TargetAlgorithm.SORT),
            config={"recursion_limit": 50},
        )
    )


# ---------- 1. success: 검증 통과 → 풀 채점셋 assembled ----------


def test_suite_pipeline_success() -> None:
    graph = _suite_graph()
    final = _run(graph, "run-suite-ok")

    assert final.final_status == "success"
    # 상류 아티팩트 (synthesis 까지 기존과 동일)
    assert final.verification is not None and final.verification.overall_pass is True
    assert len(final.candidates) == 3  # suite 노드 full-state 재emit 에도 dedup 유지
    # M4 아티팩트 — 순수 투영(Phase 3) 계약: small/large tier + 실현가능 edge
    contract = final.generator_contract
    assert contract is not None
    assert {f.name for f in contract.scale_families} == {"small", "large"}
    assert {e.name for e in contract.edge_cases} == {
        "min_size",
        "max_size",
        "empty",
        "disconnected",
    }
    suite = final.test_suite
    assert suite is not None
    assert suite.is_assembled is True
    assert suite.golden_origin == "opus"  # reconciliation.adopted_origin provenance
    # drop 없음 → 계획 전부 assembled, 카테고리 = tier + 실현가능 edge
    assert len(suite.cases) == contract.total_planned_cases
    assert {c.category for c in suite.cases} == {
        "small",
        "large",
        "min_size",
        "max_size",
        "empty",
        "disconnected",
    }
    # echo runner → expected = ans-{input} (golden 부트스트랩 정합)
    assert all(c.expected_output == f"ans-{c.input_text}" for c in suite.cases)


# ---------- 1b. Phase 5a: graph_shape 핀 → 퇴화 엣지 파생·채움 (실제 그래프) ----------


def test_resolved_edges_flow_through_real_graph() -> None:
    """graph_shape 핀 schema 면 reconciler 가 min/unreachable 퇴화 입력을 differential 에
    더하고(골든 합의 → canonical 채택), edge_filler 가 canonical golden 으로 expected 를
    채운다. 실제 컴파일 그래프로 reconciler→sample_filler→edge_filler→executor→suite 전
    경로에서 resolved_edges 가 **clobber 없이 filled 로 보존**됨을 경험적으로 검증."""
    graph = _suite_graph(formalizer_llm=_ShapedFormalizerLLM())
    final = _run(graph, "run-edge-sem")

    assert final.final_status == "success"
    edges = final.resolved_edges
    assert [e.name for e in edges] == ["min", "unreachable"]  # IR 파생됨
    # edge_filler 가 채움 — clobber 없음(executor/suite full-state 재emit 후에도 filled)
    assert all(e.expected_output is not None for e in edges)
    # edge_filler 의 full-state 반환(sample_filler twin)이 candidates reducer 를 멱등
    # 재실행해도 fan-out 폭(3)에 고정 — 더블 누적 없음(frozen 후보 값동등, M2 step4)
    assert len(final.candidates) == 3
    assert all(e.expected_output.startswith("ans-") for e in edges)  # echo golden 출력
    # 패키지 meta 표면화 (additive, 채워진 것만)
    from ipe.v2.api import _build_package

    pkg = _build_package(final, mode="p1", elapsed_s=1.0)
    assert pkg is not None
    surfaced = pkg["meta"]["resolved_edge_cases"]
    assert {e["name"] for e in surfaced} == {"min", "unreachable"}


def test_non_graph_schema_derives_no_edges() -> None:
    """비-graph(shape 미핀 = NullBackbone) → 퇴화 엣지 0 (blast radius 한정 확증)."""
    final = _run(_suite_graph(), "run-no-edge")  # 기본 _FixedFormalizerLLM = shape 미핀
    assert final.final_status == "success"
    assert final.resolved_edges == ()


# ---------- 2. verification fail → suite 미진입 ----------


def test_suite_skipped_on_verification_fail() -> None:
    # sample 은 sample_filler 가 golden 으로 채워 통과 — verification fail 은 symbolic
    # invariant violation 으로 유발 (sample mismatch 는 sample_filler 가 흡수).
    graph = _suite_graph(verifier_getter=lambda _a: _ViolatingVerifier())
    final = _run(graph, "run-suite-vfail")

    assert final.final_status == "fail_verification"
    assert final.generator_contract is None  # generator_designer 미실행
    assert final.test_suite is None  # suite 노드 미진입


# ---------- 3. partial drop: 실행 실패 입력만 drop ----------


def test_suite_partial_drop_keeps_rest() -> None:
    graph = _suite_graph(runner_fn=_fail_on_empty_graph)
    final = _run(graph, "run-suite-drop")

    assert final.final_status == "success"
    contract = final.generator_contract
    assert contract is not None
    planned = contract.total_planned_cases  # anchor 분모 보존
    suite = final.test_suite
    assert suite is not None
    assert suite.is_assembled is True
    # 'empty'('3 0') 케이스만 golden 실행 실패 → 그것만 drop, 나머지 assembled
    assert len(suite.cases) == planned - 1
    assert "empty" not in {c.category for c in suite.cases}


# ---------- 4. build guard ----------


def test_test_suite_still_requires_golden() -> None:
    # synthesis 항상 배선(Phase 4) — with_test_suite 만으로도 golden/brute 필수
    # (suite→synthesis 체인이 golden 을 요구. 옛 with_test_suite⇒with_synthesis 가드 대체).
    with pytest.raises(ValueError, match="golden_llms"):
        build_v2_graph(with_test_suite=True)
