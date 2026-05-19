"""Unit tests — M2 pre-hook infrastructure (v0.3.0 RFC §M2).

Hook registry 격리: 테스트마다 unique node_name 사용 — 기존 builtin (coder/
executor) 등록 영향 없이 검증.
"""

from __future__ import annotations

import uuid

from ipe.hooks import (
    _PRE_HOOKS,
    check_problem_complete,
    check_solution_code_present,
    check_solution_imports,
    register_pre_hook,
    run_pre_hooks,
    wrap_with_pre_hooks,
)
from ipe.state import ProblemState


def _unique_node() -> str:
    """테스트 isolation을 위한 unique node_name."""
    return f"test_node_{uuid.uuid4().hex[:8]}"


# =============================================================================
# Registry + runner
# =============================================================================


class TestRegisterPreHook:
    def test_register_adds_to_registry(self) -> None:
        node = _unique_node()
        @register_pre_hook(node)
        def my_hook(state: ProblemState) -> str | None:
            return None
        assert node in _PRE_HOOKS
        assert my_hook in _PRE_HOOKS[node]

    def test_multiple_hooks_same_node_keep_order(self) -> None:
        node = _unique_node()
        @register_pre_hook(node)
        def first(state: ProblemState) -> str | None:
            return None
        @register_pre_hook(node)
        def second(state: ProblemState) -> str | None:
            return None
        assert _PRE_HOOKS[node] == [first, second]


class TestRunPreHooks:
    def test_no_hooks_returns_none(self) -> None:
        assert run_pre_hooks(_unique_node(), {}) is None

    def test_all_pass_returns_none(self) -> None:
        node = _unique_node()
        register_pre_hook(node)(lambda s: None)
        register_pre_hook(node)(lambda s: None)
        assert run_pre_hooks(node, {}) is None

    def test_first_reject_returned(self) -> None:
        node = _unique_node()
        register_pre_hook(node)(lambda s: "first reason")
        register_pre_hook(node)(lambda s: "second reason")
        assert run_pre_hooks(node, {}) == "first reason"

    def test_short_circuit_skips_remaining(self) -> None:
        """첫 reject 후 다음 hook은 호출 안 됨 (cost 절약)."""
        node = _unique_node()
        calls: list[str] = []
        @register_pre_hook(node)
        def first(state: ProblemState) -> str | None:
            calls.append("first")
            return "reject"
        @register_pre_hook(node)
        def second(state: ProblemState) -> str | None:
            calls.append("second")
            return None
        run_pre_hooks(node, {})
        assert calls == ["first"]


class TestWrapWithPreHooks:
    def test_passes_through_when_all_hooks_pass(self) -> None:
        node = _unique_node()
        register_pre_hook(node)(lambda s: None)
        called = []
        def fn(state: ProblemState) -> ProblemState:
            called.append(True)
            return {**state, "marker": "ran"}  # type: ignore[typeddict-unknown-key]
        wrapped = wrap_with_pre_hooks(node, fn)
        out = wrapped({})
        assert called == [True]
        assert out.get("marker") == "ran"  # type: ignore[typeddict-item]

    def test_skips_fn_when_hook_rejects(self) -> None:
        node = _unique_node()
        register_pre_hook(node)(lambda s: "bad state")
        called = []
        def fn(state: ProblemState) -> ProblemState:
            called.append(True)
            return state
        wrapped = wrap_with_pre_hooks(node, fn)
        out = wrapped({})
        assert called == []
        assert out.get("last_failed_node") == node
        fb = out.get("feedback_message") or ""
        assert "bad state" in fb
        assert f"pre-hook[{node}]" in fb

    def test_preserves_existing_last_failed_node(self) -> None:
        """이미 last_failed_node가 set되어 있으면 보존."""
        node = _unique_node()
        register_pre_hook(node)(lambda s: "reject reason")
        wrapped = wrap_with_pre_hooks(node, lambda s: s)
        state: ProblemState = {"last_failed_node": "architect"}
        out = wrapped(state)
        assert out.get("last_failed_node") == "architect"


# =============================================================================
# Builtin hooks
# =============================================================================


class TestCheckSolutionCodePresent:
    def test_empty_string_rejected(self) -> None:
        assert check_solution_code_present({"solution_code": ""}) is not None  # type: ignore[typeddict-item]

    def test_whitespace_only_rejected(self) -> None:
        assert check_solution_code_present({"solution_code": "   \n  "}) is not None  # type: ignore[typeddict-item]

    def test_missing_field_rejected(self) -> None:
        assert check_solution_code_present({}) is not None

    def test_valid_code_passes(self) -> None:
        assert check_solution_code_present({"solution_code": "print(42)"}) is None  # type: ignore[typeddict-item]


class TestCheckSolutionImports:
    def test_stdlib_imports_pass(self) -> None:
        code = "import sys\nimport math\nfrom collections import deque\nprint(42)\n"
        state: ProblemState = {"solution_code": code, "target_language": "python"}
        assert check_solution_imports(state) is None

    def test_numpy_rejected(self) -> None:
        code = "import numpy as np\nprint(np.array([1,2]).sum())\n"
        state: ProblemState = {"solution_code": code, "target_language": "python"}
        reason = check_solution_imports(state)
        assert reason is not None
        assert "numpy" in reason

    def test_scipy_pandas_both_listed(self) -> None:
        code = "import scipy\nimport pandas\nprint(1)\n"
        state: ProblemState = {"solution_code": code, "target_language": "python"}
        reason = check_solution_imports(state)
        assert reason is not None
        assert "scipy" in reason
        assert "pandas" in reason

    def test_from_dotted_import_top_level_checked(self) -> None:
        """from a.b import c → a 만 검사 (top-level)."""
        code = "from numpy.random import randint\nprint(1)\n"
        state: ProblemState = {"solution_code": code, "target_language": "python"}
        reason = check_solution_imports(state)
        assert reason is not None
        assert "numpy" in reason

    def test_java_language_skipped(self) -> None:
        state: ProblemState = {
            "solution_code": "import some.random.thing",
            "target_language": "java",
        }
        assert check_solution_imports(state) is None

    def test_empty_code_passes(self) -> None:
        """다른 hook이 처리 — import 검사는 코드 없으면 vacuously pass."""
        state: ProblemState = {"solution_code": "", "target_language": "python"}
        assert check_solution_imports(state) is None


class TestCheckProblemComplete:
    def _valid_state(self) -> ProblemState:
        return {
            "problem_description": "두 수 합",
            "constraints": "1 <= a,b <= 1e9",
            "sample_testcases": [{"input": "1 2", "expected_output": "3"}],
        }

    def test_valid_passes(self) -> None:
        assert check_problem_complete(self._valid_state()) is None

    def test_missing_problem_description_rejected(self) -> None:
        state = self._valid_state()
        state["problem_description"] = ""
        reason = check_problem_complete(state)
        assert reason is not None
        assert "problem_description" in reason

    def test_missing_constraints_rejected(self) -> None:
        state = self._valid_state()
        state["constraints"] = ""
        reason = check_problem_complete(state)
        assert reason is not None
        assert "constraints" in reason

    def test_empty_samples_rejected(self) -> None:
        state = self._valid_state()
        state["sample_testcases"] = []
        reason = check_problem_complete(state)
        assert reason is not None
        assert "sample_testcases" in reason or "non-empty" in reason

    def test_multiple_missing_listed(self) -> None:
        state: ProblemState = {}
        reason = check_problem_complete(state)
        assert reason is not None
        assert "problem_description" in reason
        assert "constraints" in reason
