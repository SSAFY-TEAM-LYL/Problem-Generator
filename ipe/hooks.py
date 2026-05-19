"""Pre-hook infrastructure — M2 (v0.3.0 RFC §M2).

ECC-style ``PreToolUse`` hook 패턴을 IPE 노드 진입 직전에 적용. mandatory
정적 check가 LLM call 비용 지불 전에 invalid state를 reject한다.

Usage::

    from ipe.hooks import register_pre_hook, run_pre_hooks, wrap_with_pre_hooks

    @register_pre_hook("coder")
    def check_problem_complete(state) -> str | None:
        if not state.get("problem_description"):
            return "no problem_description"
        return None

    # graph.py:
    g.add_node("coder", wrap_with_pre_hooks("coder", partial(coder.run, tracker=tracker)))

Hook contract:
- signature: ``(state: ProblemState) -> str | None``
- return ``None`` 통과 (정상 진행)
- return ``str`` reject (사유) — 노드 실행 skip + ``last_failed_node=node_name`` self-loop
- Hook은 state read-only — mutation 금지 (race condition + immutability principle)

설계 결정 (RFC §2 M2):
- 첫 PR scope: 노드 진입 hook만 처리 (phase 전환 hook은 후속 backlog)
- 단일 reject만 보고 (첫 fail에서 short-circuit). 모든 fail 누적은 hook 개수 증가 후 검토.
- registry는 module-level dict — import 시 자동 등록 (lazy 등록 안 함)
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable

from ipe.state import ProblemState

# Registry: node_name → list of hook functions (등록 순서대로 실행)
_PRE_HOOKS: dict[str, list[Callable[[ProblemState], str | None]]] = {}


def register_pre_hook(
    node_name: str,
) -> Callable[
    [Callable[[ProblemState], str | None]],
    Callable[[ProblemState], str | None],
]:
    """Decorator — 노드 진입 직전 호출할 hook 등록.

    같은 ``node_name``에 다중 hook 가능. 등록 순서대로 실행, 첫 reject에서
    short-circuit (다음 hook은 안 부름).
    """
    def decorator(
        fn: Callable[[ProblemState], str | None],
    ) -> Callable[[ProblemState], str | None]:
        _PRE_HOOKS.setdefault(node_name, []).append(fn)
        return fn

    return decorator


def run_pre_hooks(node_name: str, state: ProblemState) -> str | None:
    """등록된 ``node_name`` pre-hook을 차례로 실행. 첫 reject 사유 반환.

    None = 모든 hook pass. str = 첫 reject 사유 (호출자가 self-loop 처리).
    """
    for hook in _PRE_HOOKS.get(node_name, []):
        reason = hook(state)
        if reason:
            return reason
    return None


def wrap_with_pre_hooks(
    node_name: str,
    fn: Callable[[ProblemState], ProblemState],
) -> Callable[[ProblemState], ProblemState]:
    """노드 함수를 pre-hook으로 감싸 LangGraph에 등록할 callable 반환.

    pre-hook reject 시 노드 실행 skip + state에 ``feedback_message`` /
    ``last_failed_node`` 설정 후 반환. graph의 decision 노드가 후속 라우팅 처리.
    """
    def wrapped(state: ProblemState) -> ProblemState:
        reason = run_pre_hooks(node_name, state)
        if reason:
            return {
                **state,
                "feedback_message": f"pre-hook[{node_name}]: {reason}",
                "last_failed_node": state.get("last_failed_node") or node_name,
            }
        return fn(state)

    return wrapped


# ============================================================================
# Built-in hooks (v0.3.0 첫 set — 3개)
# ============================================================================

# Python 표준 라이브러리 외 import 차단 — solution은 self-contained여야 함.
# 외부 패키지 (numpy, pandas 등)는 sandbox image (python:3.11-slim)에 없으므로 RTE.
#
# Manually-maintained allow-list는 fragile — Python 3.10+의 ``sys.stdlib_module_names``
# 가 정확한 최신 stdlib 리스트 제공 (Python 3.11에서 305 modules). hot-fix:
# 이전 hardcoded set이 ``ctypes`` / ``tempfile`` 등 누락 → 정상 솔루션 false reject
# (Round 20 e2e smoke에서 발견).
#
# ``__future__`` 는 stdlib_module_names에 포함됨 (확인됨).
_PYTHON_STDLIB: frozenset[str] = frozenset(sys.stdlib_module_names)

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


@register_pre_hook("executor")
def check_solution_code_present(state: ProblemState) -> str | None:
    """executor 진입 직전 — solution_code가 비어있지 않은지 확인.

    coder가 IMPOSSIBLE 선언 시 ``last_failed_node="architect"``이므로 이 hook은
    coder 정상 출력 후에만 fail. coder가 응답을 비워 보낸 edge case 사전 차단.
    """
    code = state.get("solution_code")
    if not code or not str(code).strip():
        return "solution_code is empty — coder must produce a solution"
    return None


@register_pre_hook("executor")
def check_solution_imports(state: ProblemState) -> str | None:
    """executor 진입 직전 — solution에 표준 라이브러리 외 import 차단.

    sandbox image (python:3.11-slim)에는 외부 패키지 없음. ``numpy`` /
    ``scipy`` 등 import 시 ModuleNotFoundError 즉시 발생 → Phase A RTE.
    정적으로 사전 reject하여 LLM call 1회 절약.

    target_language=python 한정 — Java/기타 언어는 무조건 pass.
    """
    if state.get("target_language", "python") != "python":
        return None
    code = state.get("solution_code") or ""
    forbidden: list[str] = []
    for m in _IMPORT_RE.finditer(str(code)):
        mod = m.group(1).split(".")[0]
        if mod not in _PYTHON_STDLIB:
            forbidden.append(mod)
    if forbidden:
        unique = sorted(set(forbidden))[:5]
        return (
            f"solution uses non-stdlib imports: {unique}. "
            f"sandbox has Python stdlib only — rewrite without these."
        )
    return None


@register_pre_hook("coder")
def check_problem_complete(state: ProblemState) -> str | None:
    """coder 진입 직전 — architect 출력이 완전한지 확인.

    architect가 정상 응답 후에야 coder가 의미 있는 작업 가능. problem
    필드가 누락된 채 coder 호출되는 edge case 사전 차단.
    """
    missing: list[str] = []
    for field in ("problem_description", "constraints", "sample_testcases"):
        val = state.get(field)
        if not val:
            missing.append(field)
    if missing:
        return (
            f"architect output incomplete — missing: {missing}. "
            f"architect must populate these before coder can implement."
        )
    samples = state.get("sample_testcases") or []
    if not isinstance(samples, list) or len(samples) < 1:
        return "sample_testcases must be a non-empty list"
    return None


__all__ = [
    "register_pre_hook",
    "run_pre_hooks",
    "wrap_with_pre_hooks",
    "check_solution_code_present",
    "check_solution_imports",
    "check_problem_complete",
]
