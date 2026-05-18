"""R-gen-cap — Generator hard cap validator unit tests.

Generator 노드의 sandbox 외부 사전 검증 — LLM이 생성한 generator script를
실제 실행하여 출력 size가 ``MAX_GENERATED_INPUT_BYTES`` 초과 시 즉시 self-loop.

Phase C에서 fail이 일어나는 기존 흐름은:
    Phase C → gen_fail → Generator self-loop → LLM 동일 패턴 재생성 → 무한

R-gen-cap는:
    Generator 노드 → cap 검증 → 초과 시 즉시 self-loop + 정확한 size feedback
    → LLM이 명확한 신호로 다음 응답 조정

스펙: CHANGES.md §16.3, docs/improvements/2026-05-18_gen-cap-deterministic.md
"""

from __future__ import annotations

from pathlib import Path

from ipe.nodes._executor_helpers import MAX_GENERATED_INPUT_BYTES
from ipe.nodes.generator import _validate_generator_caps
from ipe.sandbox.runner import RunResult, RunSpec, SandboxedRunner


class _FakeRunner(SandboxedRunner):
    """결정적 unit test용 fake — 미리 준비한 RunResult를 순서대로 반환."""

    tier = "FAKE"

    def __init__(self, results: list[RunResult]) -> None:
        self._results = list(results)
        self._idx = 0
        self.calls: list[RunSpec] = []

    def run(self, spec: RunSpec) -> RunResult:
        self.calls.append(spec)
        if self._idx >= len(self._results):
            raise RuntimeError(
                f"FakeRunner exhausted at call {self._idx + 1}, "
                f"only {len(self._results)} results prepared"
            )
        r = self._results[self._idx]
        self._idx += 1
        return r

    def isolation_self_test(self) -> dict[str, bool]:
        return {}


def _ok(stdout: str = "small output\n") -> RunResult:
    return RunResult(
        status="OK", returncode=0, stdout=stdout, stderr="",
        elapsed_ms=10, truncated_stdout=False,
    )


def _ole(stdout: str = "") -> RunResult:
    """sandbox가 cap 초과로 truncate한 결과 (Output Limit Exceeded)."""
    return RunResult(
        status="OLE", returncode=0, stdout=stdout, stderr="",
        elapsed_ms=10, truncated_stdout=True,
    )


def _rte(stderr: str = "TypeError: ...") -> RunResult:
    return RunResult(
        status="RTE", returncode=1, stdout="", stderr=stderr,
        elapsed_ms=10, truncated_stdout=False,
    )


def _g(name: str, code: str = "print(1)", seeds: tuple[int, ...] = (1, 2, 3)) -> dict:
    return {"name": name, "category": "RANDOM_SMALL",
            "description": "test", "code": code, "seeds": list(seeds)}


# =============================================================================
# _validate_generator_caps — 결정적 사전 검증
# =============================================================================


class TestValidateGeneratorCaps:
    def test_empty_generators_returns_none(self, tmp_path: Path) -> None:
        """generators 비어있으면 검증할 게 없음 → None."""
        runner = _FakeRunner([])
        assert _validate_generator_caps([], runner, tmp_path) is None

    def test_all_under_cap_returns_none(self, tmp_path: Path) -> None:
        """모든 generator OK → None (Executor 진입)."""
        runner = _FakeRunner([_ok(), _ok(), _ok()])
        gens = [_g("gen_small"), _g("gen_medium"), _g("gen_max")]
        assert _validate_generator_caps(gens, runner, tmp_path) is None
        assert len(runner.calls) == 3  # 각 generator 1번씩

    def test_single_cap_exceed_reports_size(self, tmp_path: Path) -> None:
        """OLE (cap 초과) 발견 시 generator 이름 + cap 정보 포함."""
        runner = _FakeRunner([_ok(), _ole(), _ok()])
        gens = [_g("gen_a"), _g("gen_b"), _g("gen_c")]
        feedback = _validate_generator_caps(gens, runner, tmp_path)
        assert feedback is not None
        assert "gen_b" in feedback
        assert str(MAX_GENERATED_INPUT_BYTES) in feedback or "2097152" in feedback

    def test_multiple_cap_exceeds_all_reported(self, tmp_path: Path) -> None:
        """다중 cap 초과 — 모든 위반 generator를 한 번에 보고 (early exit 아님)."""
        runner = _FakeRunner([_ole(), _ok(), _ole()])
        gens = [_g("gen_x"), _g("gen_y"), _g("gen_z")]
        feedback = _validate_generator_caps(gens, runner, tmp_path)
        assert feedback is not None
        assert "gen_x" in feedback
        assert "gen_z" in feedback
        # 모든 generator를 다 실행했어야 함 (early exit 금지)
        assert len(runner.calls) == 3

    def test_rte_treated_as_reject(self, tmp_path: Path) -> None:
        """sandbox RTE도 reject 사유 — generator script 자체 오류."""
        runner = _FakeRunner([_rte(stderr="ImportError: numpy")])
        gens = [_g("gen_broken")]
        feedback = _validate_generator_caps(gens, runner, tmp_path)
        assert feedback is not None
        assert "gen_broken" in feedback
        assert "RTE" in feedback or "ImportError" in feedback

    def test_skips_generators_without_seeds(self, tmp_path: Path) -> None:
        """seeds 비어있는 generator는 검증 skip (실행 불가, 다른 검증 단계에서 reject)."""
        runner = _FakeRunner([_ok()])
        gens = [_g("gen_a", seeds=()), _g("gen_b")]
        feedback = _validate_generator_caps(gens, runner, tmp_path)
        assert feedback is None
        assert len(runner.calls) == 1  # gen_b만 실행

    def test_runner_called_with_first_seed(self, tmp_path: Path) -> None:
        """첫 번째 seed로만 실행 (모든 seed 다 돌리지는 않음 — Phase C에서)."""
        runner = _FakeRunner([_ok()])
        gens = [_g("gen_a", seeds=(7, 8, 9))]
        _validate_generator_caps(gens, runner, tmp_path)
        # spec.cmd에 seed=7이 있어야 함
        assert any("7" in arg for arg in runner.calls[0].cmd)

    def test_generator_script_written_to_workdir(self, tmp_path: Path) -> None:
        """generator code가 workdir에 .py로 저장됨 (sandbox가 실행할 수 있도록)."""
        runner = _FakeRunner([_ok()])
        gens = [_g("gen_test", code="print('hello')")]
        _validate_generator_caps(gens, runner, tmp_path)
        scripts = list(tmp_path.rglob("gen_test.py"))
        assert len(scripts) == 1
        assert "hello" in scripts[0].read_text(encoding="utf-8")

    def test_ole_with_large_stdout_reports_actual_size(self, tmp_path: Path) -> None:
        """OLE인데 stdout이 부분적으로 들어왔으면 부분 size라도 보고."""
        big = "x" * MAX_GENERATED_INPUT_BYTES
        runner = _FakeRunner([_ole(stdout=big)])
        gens = [_g("gen_huge")]
        feedback = _validate_generator_caps(gens, runner, tmp_path)
        assert feedback is not None
        assert "gen_huge" in feedback
