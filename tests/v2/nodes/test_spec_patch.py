"""spec_patch 노드 단위 테스트 (Phase 3 B — QA back-route). LLM 없음.

revise 된 narrative 의 scenario→spec.description, title→spec.title 반영 — io_contract
(canonical 동결 렌더)/샘플/target_algorithm 은 보존해 verified golden·suite 를 무효화하지
않는다 (synthesis 재실행 없는 싼 back-route 의 핵심). title 도 patch 하는 이유: Phase 4
에서 ``spec.title = narrative.title`` 로 결합돼 revise 된 title 이 따라가야 한다.
"""

from __future__ import annotations

import pytest

from ipe.v1.schema import (
    IOContract,
    Narrative,
    ProblemSpec,
    SampleTestCase,
    TargetAlgorithm,
)
from ipe.v2.nodes import make_spec_patch_node
from ipe.v2.state import initial_v2_state


def _spec() -> ProblemSpec:
    return ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="OLD title",
        description="OLD scenario",
        io_contract=IOContract(input_format="V E ...", output_format="int"),
        sample_testcases=[
            SampleTestCase(input_text=f"{i} 0 1 1", expected_output="0")
            for i in range(1, 4)  # ProblemSpec 최소 3개 요구
        ],
    )


def test_spec_patch_replaces_description_and_title() -> None:
    state = initial_v2_state("r", TargetAlgorithm.DIJKSTRA).model_copy(
        update={
            "spec": _spec(),
            "narrative": Narrative(
                title="NEW title", scenario="NEW scenario", hidden=True, domain="d"
            ),
        }
    )
    out = make_spec_patch_node()(state)
    assert isinstance(out, dict)
    patched = out["spec"]
    assert patched.description == "NEW scenario"
    assert patched.title == "NEW title"  # revise 된 narrative.title 반영 (Phase 4 결합)
    assert state.spec is not None
    assert patched.io_contract == state.spec.io_contract  # canonical 렌더 보존
    assert patched.sample_testcases == state.spec.sample_testcases  # 샘플 보존
    assert patched.target_algorithm is TargetAlgorithm.DIJKSTRA


def test_spec_patch_requires_spec_and_narrative() -> None:
    bare = initial_v2_state("r", TargetAlgorithm.DIJKSTRA)
    with pytest.raises(ValueError, match="spec"):
        make_spec_patch_node()(bare)
    only_spec = bare.model_copy(update={"spec": _spec()})
    with pytest.raises(ValueError, match="narrative"):
        make_spec_patch_node()(only_spec)
