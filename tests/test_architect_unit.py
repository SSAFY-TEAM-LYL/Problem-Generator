"""architect.py 단위 테스트 (polish round 2 — B3 해소).

스펙: PROJECT_SPEC.md §4.1, IMPLEMENTATION_ROADMAP §1 P4
범위: ``_validate_constraints_structured`` 7 분기 + ``_route_back`` + parse error.

기존 통합 테스트 (``tests/integration/test_architect_phase_a.py``)는 happy/major
paths만 cover — 본 단위 테스트가 edge cases 보강.
"""

from __future__ import annotations

from typing import Any

import pytest

from ipe.nodes.architect import (
    ConstraintValidationError,
    _route_back,
    _validate_constraints_structured,
)
from ipe.state import LLMCallRecord, ProblemState

# =============================================================================
# _validate_constraints_structured — 7 raise 분기
# =============================================================================


class TestValidateConstraintsStructured:
    def _valid_cs(self) -> dict[str, Any]:
        return {"time_limit_ms": 2000, "memory_limit_mb": 256}

    def test_valid_minimal_passes(self) -> None:
        # variables 없이도 통과 (변수 정보 부재로 over-restriction 회피)
        _validate_constraints_structured(self._valid_cs())

    def test_valid_with_variables_passes(self) -> None:
        cs = self._valid_cs()
        cs["variables"] = [
            {"name": "N", "min": 1, "max": 1000},
            {"name": "M", "min": 0, "max": 100, "type": "int"},
        ]
        _validate_constraints_structured(cs)

    def test_non_dict_raises(self) -> None:
        """cs가 dict가 아니면 raise (line 80)."""
        with pytest.raises(ConstraintValidationError, match="must be an object"):
            _validate_constraints_structured("not a dict")
        with pytest.raises(ConstraintValidationError, match="must be an object"):
            _validate_constraints_structured([])

    def test_missing_time_limit_raises(self) -> None:
        with pytest.raises(ConstraintValidationError, match="time_limit_ms required"):
            _validate_constraints_structured({"memory_limit_mb": 256})

    def test_non_int_time_limit_raises(self) -> None:
        """time_limit_ms가 int 아니면 raise (line 84)."""
        with pytest.raises(ConstraintValidationError, match="time_limit_ms must be int"):
            _validate_constraints_structured(
                {"time_limit_ms": "2000", "memory_limit_mb": 256}
            )

    def test_missing_memory_limit_raises(self) -> None:
        with pytest.raises(ConstraintValidationError, match="memory_limit_mb required"):
            _validate_constraints_structured({"time_limit_ms": 2000})

    def test_non_int_memory_limit_raises(self) -> None:
        """memory_limit_mb가 int 아니면 raise (line 88)."""
        with pytest.raises(ConstraintValidationError, match="memory_limit_mb must be int"):
            _validate_constraints_structured(
                {"time_limit_ms": 2000, "memory_limit_mb": 256.5}
            )

    def test_variables_not_list_raises(self) -> None:
        """variables가 list 아니면 raise (line 92)."""
        cs = self._valid_cs()
        cs["variables"] = "not a list"
        with pytest.raises(ConstraintValidationError, match="variables must be a list"):
            _validate_constraints_structured(cs)

    def test_variable_entry_not_dict_raises(self) -> None:
        """variables[] entries가 dict 아니면 raise (line 95)."""
        cs = self._valid_cs()
        cs["variables"] = ["not a dict"]
        with pytest.raises(ConstraintValidationError, match="entries must be objects"):
            _validate_constraints_structured(cs)

    def test_variable_missing_name_raises(self) -> None:
        cs = self._valid_cs()
        cs["variables"] = [{"min": 1, "max": 100}]  # name 누락
        with pytest.raises(ConstraintValidationError, match="missing required field: name"):
            _validate_constraints_structured(cs)

    def test_variable_missing_min_raises(self) -> None:
        cs = self._valid_cs()
        cs["variables"] = [{"name": "N", "max": 100}]
        with pytest.raises(ConstraintValidationError, match="missing required field: min"):
            _validate_constraints_structured(cs)

    def test_variable_missing_max_raises(self) -> None:
        """variables[] missing max raise (line 98)."""
        cs = self._valid_cs()
        cs["variables"] = [{"name": "N", "min": 1}]
        with pytest.raises(ConstraintValidationError, match="missing required field: max"):
            _validate_constraints_structured(cs)


# =============================================================================
# _route_back — self-loop signal 빌더
# =============================================================================


class TestRouteBack:
    def test_basic_route_back(self) -> None:
        state: ProblemState = {"target_algorithm": "Two Sum"}
        calls: list[LLMCallRecord] = [
            {"seq": 1, "node": "architect", "model": "x", "input_tokens": 0,
             "output_tokens": 0, "cost_usd": 0.0, "timestamp": "", "trace_path": ""},
        ]
        result = _route_back(state, calls, "missing fields: foo, bar")

        # 기본 state 보존
        assert result["target_algorithm"] == "Two Sum"
        # routing 시그널 set
        assert result["last_failed_node"] == "architect"
        assert result["feedback_message"] == "missing fields: foo, bar"
        # llm_calls가 인자값으로 set
        assert result["llm_calls"] == calls

    def test_overrides_existing_feedback(self) -> None:
        """기존 feedback_message가 있어도 새 reason으로 덮어씀."""
        state: ProblemState = {"feedback_message": "old"}
        result = _route_back(state, [], "new reason")
        assert result["feedback_message"] == "new reason"
