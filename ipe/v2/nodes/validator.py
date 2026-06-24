"""IR validator 노드 — formalizer freeze 직후 **순수코드** well-formedness 게이트 (RFC §6).

세 검증 관계 중 **IR ↔ 자기**(전역에서 well-defined 한 단일값 함수 명세인가)를 본다 —
faithfulness(narrative↔IR)·reconcile(golden↔IR)와 짝을 이루는 세 번째 게이트. 이전엔
ill-posed IR 를 잡는 유일 신호가 reconcile(golden×K 발산)뿐이라 **full synthesis 이후**
에야, 그것도 back-route 없이 죽었다. validator 는 그 신호를 synthesis **전**의 싸고
진단적이고 수선 가능한 front gate 로 끌어온다.

Tier A (순수코드, 항상 on):
- **완전성** — collection 필드(array/matrix/graph)는 size_range 필수.
- **참조 해소** — references 는 존재하는 **sized 컬렉션** 을 가리켜야 (dangling/비-collection 금지).
- **P2 well-formedness** — composed 모드면 composition 비어있지 않음.

realizability/coverage(backbone ``derive_edge_inputs`` 의 realizable-degeneracy + ResolvedEdgeCase
slot)·orphan-field 는 후속 phase (Phase 5 / richer IR). LLM 없음 — 순수 함수 + node 래퍼.
"""

from __future__ import annotations

from collections.abc import Callable

from ipe.v1.schema import IRValidationReport, ProblemBlueprint

from ..config import PipelineMode
from ..state import V2State

# canonical 직렬화에 자기 크기 헤더를 갖는 collection 타입 (스칼라 참조의 바인딩 대상).
_COLLECTION_TYPES = ("int_array", "int_matrix", "grid", "weighted_edges", "tree_edges")


def validate_ir(
    blueprint: ProblemBlueprint, *, mode: PipelineMode
) -> IRValidationReport:
    """ProblemBlueprint → Tier A well-formedness 진단 (순수코드).

    violations 가 비어있으면 valid=True. 각 violation 은 사람이 읽는 진단 문장 —
    back-route 시 formalizer 가 이것을 받아 io_schema 를 수선한다.
    """
    io = blueprint.io_schema
    by_name = {f.name: f for f in io.inputs}
    violations: list[str] = []

    for f in io.inputs:
        # (1) 완전성 — collection 은 크기 미정이면 입력 생성·제약 파생이 정의 불가
        if f.type in _COLLECTION_TYPES and f.size_range is None:
            violations.append(
                f"완전성: collection 필드 '{f.name}'({f.type}) 에 size_range 누락 "
                "— 크기 미정이라 입력 생성·제약이 정의되지 않는다"
            )
        # (2) 참조 해소 — references 는 존재하는 sized 컬렉션을 가리켜야
        if f.type == "int" and f.references is not None:
            target = by_name.get(f.references)
            if target is None:
                violations.append(
                    f"참조: 스칼라 '{f.name}' 가 존재하지 않는 필드 "
                    f"'{f.references}' 를 가리킴 (dangling reference)"
                )
            elif target.type not in _COLLECTION_TYPES:
                violations.append(
                    f"참조: 스칼라 '{f.name}' 가 비-collection 필드 "
                    f"'{f.references}'({target.type}) 를 가리킴 — 크기 참조 불가"
                )

    # (3) P2 well-formedness — composed 인데 composition 이 비면 합성 미실현 IR
    if mode == "p2" and not blueprint.composition:
        violations.append(
            "P2 well-formedness: composition 이 비어있음 — 합성(composed) 모드인데 "
            "합성 기법이 없어 단일 알고리즘과 구분되지 않는다"
        )

    return IRValidationReport(valid=not violations, violations=tuple(violations))


def make_validator_node(*, mode: PipelineMode) -> Callable[[V2State], V2State]:
    """factory — formalizer 가 freeze 한 blueprint 를 Tier A 검사 (순수코드, LLM 없음).

    ``state.validation`` 에 report 기록만 한다. invalid 시 formalizer back-route 라우팅
    (route_after_validator)은 graph 책임 — 본 노드는 report emit 에 집중 (단일 책임).
    """

    def node(state: V2State) -> V2State:
        bp = state.blueprint
        if bp is None:
            msg = "validator requires state.blueprint — formalizer must run first"
            raise ValueError(msg)
        report = validate_ir(bp, mode=mode)
        return state.model_copy(update={"validation": report})

    return node
