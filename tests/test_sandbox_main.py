"""``python -m ipe.sandbox`` 단위 테스트 (polish round 3 — subprocess coverage 해소).

스펙: ARCHITECTURE.md §3.1, IMPLEMENTATION_ROADMAP §1 P12.4
범위: ``ipe.sandbox.__main__.main()`` 직접 호출 (sys.argv monkeypatch 우회).

기존 ``tests/integration/test_cli_smoke.py::TestSandboxCli``는 subprocess.run으로
호출 — coverage 측정 불가 (사용자 프로세스 외부). 본 파일이 ``main()`` 함수를
직접 호출하여 ``sandbox/__main__.py`` 0% → ~92% 해소 (post-p12 backlog 항목).
"""

from __future__ import annotations

import json

import pytest

from ipe.sandbox.__main__ import main as sandbox_main


def test_main_rlimit_returns_zero_or_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--tier rlimit`` → main() 동작 + isolation 결과 stdout JSON.

    rlimit(T3)은 POSIX 한계로 일부 isolation fail 가능 — exit 0 또는 1 모두 valid.
    """
    monkeypatch.setattr("sys.argv", ["ipe.sandbox", "--tier", "rlimit"])
    rc = sandbox_main()

    assert rc in (0, 1)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "T3" in out or "rlimit" in out.lower()
    assert "network_blocked" in out or "isolation" in out.lower()


def test_main_default_tier_auto(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--tier`` 미지정 → default ``auto`` → pick_runner가 환경에 맞게 선택."""
    monkeypatch.setattr("sys.argv", ["ipe.sandbox"])
    rc = sandbox_main()

    assert rc in (0, 1, 2)
    captured = capsys.readouterr()
    assert "Using runner" in captured.out or "runner" in captured.out.lower()


def test_main_invalid_tier_argparse_error(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """잘못된 tier → argparse가 SystemExit 발생."""
    monkeypatch.setattr("sys.argv", ["ipe.sandbox", "--tier", "bogus_tier"])
    with pytest.raises(SystemExit) as excinfo:
        sandbox_main()
    assert excinfo.value.code == 2


def test_main_runner_instantiation_failure_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``pick_runner`` 가 RuntimeError → exit 2 + stderr error 메시지."""
    def _failing_runner(*args: object, **kwargs: object) -> object:
        raise RuntimeError("simulated runner instantiation failure")

    monkeypatch.setattr("ipe.sandbox.__main__.pick_runner", _failing_runner)
    monkeypatch.setattr("sys.argv", ["ipe.sandbox", "--tier", "rlimit"])
    rc = sandbox_main()

    assert rc == 2
    captured = capsys.readouterr()
    assert "Failed to instantiate runner" in captured.err
    assert "simulated runner instantiation failure" in captured.err


def test_main_all_pass_returns_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """isolation_self_test 전부 True → exit 0 + ✅ 메시지."""
    class _MockRunner:
        tier = "MOCK"

        def isolation_self_test(self) -> dict[str, bool]:
            return {"network_blocked": True, "fs_write_blocked": True,
                    "memory_limited": True, "cpu_limited": True}

    monkeypatch.setattr(
        "ipe.sandbox.__main__.pick_runner", lambda *a, **k: _MockRunner()
    )
    monkeypatch.setattr("sys.argv", ["ipe.sandbox", "--tier", "rlimit"])
    rc = sandbox_main()

    assert rc == 0
    captured = capsys.readouterr()
    assert "✅" in captured.out
    assert "true" in captured.out.lower()


def test_main_partial_fail_returns_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """isolation_self_test 일부 False → exit 1 + 실패 키 목록."""
    class _PartialRunner:
        tier = "MOCK"

        def isolation_self_test(self) -> dict[str, bool]:
            return {"network_blocked": False, "fs_write_blocked": True,
                    "memory_limited": False, "cpu_limited": True}

    monkeypatch.setattr(
        "ipe.sandbox.__main__.pick_runner", lambda *a, **k: _PartialRunner()
    )
    monkeypatch.setattr("sys.argv", ["ipe.sandbox", "--tier", "rlimit"])
    rc = sandbox_main()

    assert rc == 1
    captured = capsys.readouterr()
    out = captured.out
    assert "failed checks" in out
    json_start = out.find("{")
    json_end = out.find("}", json_start) + 1
    parsed = json.loads(out[json_start:json_end])
    assert parsed["network_blocked"] is False
    assert parsed["fs_write_blocked"] is True
