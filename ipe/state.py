"""IPE 공유 상태 정의 — LangGraph 노드 사이로 흘려보내는 dict 타입.

스펙: PROJECT_SPEC.md §2 (Global State Schema)

런타임 동작은 일반 dict와 동일하나, 타입 체커가 잘못된 키 접근을 잡아낸다.
모든 TypedDict는 `total=False` — 노드를 거치며 점진적으로 채워지므로 부분
완성 상태가 정상.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class ConstraintSpec(TypedDict, total=False):
    """구조화된 제약조건. Executor가 problem별 timeout/memlimit를 enforce."""

    variables: list[dict[str, Any]]  # [{name, min, max, type}]
    time_limit_ms: int
    memory_limit_mb: int
    raw: str


class IterationRecord(TypedDict, total=False):
    """시도 이력 한 항목. feedback에 동봉되어 oscillation 방지."""

    iter_index: int
    node: str
    action: str
    error_signature: str
    feedback: str


class LLMCallRecord(TypedDict, total=False):
    """LLM 호출 한 건. 비용 추적 + 재현용 trace 경로."""

    seq: int
    node: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: str
    trace_path: str


class NodeRetryBudget(TypedDict, total=False):
    """노드별 잔여 재시도 횟수. SPEC §5 기본값: architect=2, coder=4, auditor=2, generator=2.

    M1 (v0.3.0 RFC §M1): ``algorithm_designer`` 추가 — Coder 분해의 designer 측.
    default 2 (architect와 동일 — design 시도 횟수 제한).
    """

    architect: int
    algorithm_designer: int
    coder: int
    auditor: int
    generator: int


FinalStatus = Literal[
    "success",
    "max_iterations",
    "budget_exhausted",
    "cost_exceeded",
]


class ProblemState(TypedDict, total=False):
    """LangGraph 노드 사이로 흘려보내는 공유 상태."""

    # Meta / control
    run_id: str
    target_algorithm: str
    target_language: str
    iteration_count: int
    max_iter: int
    node_retry_budget: NodeRetryBudget
    max_cost_usd: float | None

    # Architect output
    problem_title: str
    problem_description: str
    constraints: str
    constraints_structured: ConstraintSpec
    sample_testcases: list[dict[str, Any]]
    has_special_judge: bool
    special_judge_code: str | None

    # M1 (v0.3.0 RFC §M1) — AlgorithmDesigner output. Coder 분해의 designer 출력.
    # schema: ``{name, pseudocode, complexity_target, edge_cases: list[str]}``.
    # Coder가 이 출력을 prompt에 포함하여 implementation 품질 ↑ (ECC subagent 패턴).
    # 없으면 (legacy path) Coder는 problem만 보고 implementation.
    algorithm_design: dict[str, Any]

    # M3 (v0.3.0 RFC §M3) — Multi-model consensus for Architect. **ROLLED BACK
    # 2026-05-21** — A/B 측정 결과 net effect 0 ~ 음 (Dijkstra baseline 3/3 vs
    # IPE 0/3). architect 가 single Opus call 로 복귀. 본 필드는 backward compat
    # 위해 schema 에 보존 (기존 problem.json 직렬화 데이터 read 가능). 신규 run
    # 에서는 더 이상 채워지지 않음.
    architect_candidates: list[dict[str, Any]]
    architect_consensus: str

    # M4 (v0.3.0 RFC §M4) — Adversarial review on Coder solution.
    # ``review_status``: "approved" | "rejected" — Reviewer 판정.
    # ``review_reasoning``: 한 문장 요약 (분석/관측용).
    # ``review_weaknesses``: list[str] — reject 시 coder feedback에 동봉되는 약점들.
    # approve → executor 진입, reject → coder retry (last_failed_node="coder").
    review_status: str
    review_reasoning: str
    review_weaknesses: list[str]

    # Coder output
    solution_code: str
    # R13 (Sprint 3): Coder가 매 cycle 응답 시작 시 출력하는 1-line "LESSON"
    # 누적. W4 oscillation prompt-only 강제의 진화 — 추상 "다른 전략" 대신
    # 구체 "왜 fail / 어떤 strategy" 학습이 history에 쌓여 다음 cycle에 노출.
    lessons_learned: list[str]
    # R15 (Sprint 3): Coder가 동시 작성하는 brute solution (O(N²) 등 naive).
    # Phase C에서 small N stress (input_bytes ≤ 1KB) 케이스에 대해 golden과
    # cross-check — 알고리즘 도메인 특화 deterministic 검증 신호. LLM 비결정성
    # 과 무관하게 정확성 ↑. brute가 없으면 (LLM 형식 어김) cross-check 생략.
    brute_solution_code: str
    # R14 (Sprint 3): Coder Best-of-N fanout. >1이면 N개 솔루션 동시 생성
    # (temperature 변동). default 1 (opt-in, 회귀 0). CLI ``--coder-fanout N``.
    coder_fanout: int
    # R14: Coder가 fanout N으로 생성한 후보 솔루션 리스트. 각 dict는
    # ``{code, brute, lesson, temperature}`` — Executor가 sample 검증 후
    # best (fail count 최소) 선택 (별도 PR). 현 PR은 구조만 도입, best 선택은
    # 첫 번째 후보 단순 채택 — 진짜 best는 다음 PR.
    candidate_solutions: list[dict[str, Any]]

    # Auditor output
    adversarial_inputs: list[dict[str, Any]]

    # Generator output
    generators: list[dict[str, Any]]

    # Executor output
    testcases: list[dict[str, Any]]
    execution_results: list[dict[str, Any]]
    feedback_message: str | None
    last_failed_node: str | None
    final_status: FinalStatus | None

    # Iteration / observability
    iteration_history: list[IterationRecord]
    llm_calls: list[LLMCallRecord]

    # Evaluator output
    difficulty_label: str | None
    difficulty_reasoning: str | None
    difficulty_factors: dict[str, Any] | None
    difficulty_calibration_anchors: list[dict[str, Any]] | None
