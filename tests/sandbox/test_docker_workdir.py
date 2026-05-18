"""R-docker-workdir (Round 15) — DockerRunner cwd 절대경로 자동 변환 회귀 방지.

배경: Round 14 e2e BFS/SegTree Docker run에서 main.py의 ``WORKDIR_ROOT = Path("workdir")``
상대경로 → DockerRunner ``--workdir=workdir/run_xxx`` → Docker daemon이 거부:
    "docker: Error response from daemon: the working directory '...' is invalid,
     it needs to be an absolute path"
→ 모든 sample이 RTE → e2e 측정 불가.

해법: DockerRunner.run() 진입 시 ``Path(spec.cwd).resolve()``로 자동 절대화 +
main.py에서도 OUTPUTS_ROOT/WORKDIR_ROOT를 ``.resolve()`` 처리 (이중 안전).

본 unit은 mock subprocess로 cmd 인자 검증 — Docker daemon 없이 결정적.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ipe.sandbox.docker_runner import DockerRunner
from ipe.sandbox.runner import RunSpec


def _make_runner_no_init() -> DockerRunner:
    """DockerRunner를 생성하되 __init__의 docker version check 우회 (테스트 환경 무관)."""
    runner = DockerRunner.__new__(DockerRunner)
    runner.image = "python:3.11-slim"
    return runner


def _captured_cmd(call_args: tuple) -> list[str]:
    """patch된 subprocess.run의 첫 번째 인자(cmd list) 추출."""
    args, _kwargs = call_args
    return list(args[0])


class TestDockerWorkdirResolution:
    """DockerRunner.run()이 spec.cwd를 절대경로로 변환하는지 검증."""

    def test_relative_cwd_resolved_to_absolute_in_workdir(self) -> None:
        """``cwd="workdir/run_xx"`` → ``--workdir=/abs/.../workdir/run_xx``."""
        runner = _make_runner_no_init()
        spec = RunSpec(cmd=["echo", "hi"], cwd="workdir/run_test")

        with patch("ipe.sandbox.docker_runner.subprocess.run") as m:
            mock_proc = MagicMock(returncode=0, stdout="ok\n", stderr="")
            m.return_value = mock_proc
            runner.run(spec)

        cmd = _captured_cmd(m.call_args)
        workdir_args = [a for a in cmd if a.startswith("--workdir=")]
        assert len(workdir_args) == 1
        wd_value = workdir_args[0][len("--workdir="):]
        assert Path(wd_value).is_absolute(), f"--workdir must be absolute, got {wd_value!r}"
        assert wd_value.endswith("workdir/run_test")

    def test_relative_cwd_resolved_in_tmpfs(self) -> None:
        """``--tmpfs=<cwd>:...`` 인자도 절대경로로 변환."""
        runner = _make_runner_no_init()
        spec = RunSpec(cmd=["echo", "hi"], cwd="rel/path", memory_limit_mb=256)

        with patch("ipe.sandbox.docker_runner.subprocess.run") as m:
            m.return_value = MagicMock(returncode=0, stdout="", stderr="")
            runner.run(spec)

        cmd = _captured_cmd(m.call_args)
        tmpfs_args = [a for a in cmd if a.startswith("--tmpfs=")]
        assert len(tmpfs_args) == 1
        tmpfs_value = tmpfs_args[0][len("--tmpfs="):]
        path_part = tmpfs_value.split(":", 1)[0]
        assert Path(path_part).is_absolute(), f"--tmpfs path must be absolute, got {path_part!r}"

    def test_absolute_cwd_stays_absolute(self) -> None:
        """이미 절대경로면 절대경로 유지 (정확한 문자열은 OS symlink 해석에 따라 다를 수 있음)."""
        runner = _make_runner_no_init()
        spec = RunSpec(cmd=["echo", "hi"], cwd="/tmp/already_abs")

        with patch("ipe.sandbox.docker_runner.subprocess.run") as m:
            m.return_value = MagicMock(returncode=0, stdout="", stderr="")
            runner.run(spec)

        cmd = _captured_cmd(m.call_args)
        workdir_args = [a for a in cmd if a.startswith("--workdir=")]
        assert len(workdir_args) == 1
        wd_value = workdir_args[0][len("--workdir="):]
        assert Path(wd_value).is_absolute()
        # macOS: /tmp → /private/tmp symlink. resolve는 정규화하지만 끝부분은 보존.
        assert wd_value.endswith("already_abs")

    def test_dotted_relative_cwd_resolved(self) -> None:
        """``./foo`` 같은 명시 상대경로도 절대화."""
        runner = _make_runner_no_init()
        spec = RunSpec(cmd=["echo", "hi"], cwd="./local")

        with patch("ipe.sandbox.docker_runner.subprocess.run") as m:
            m.return_value = MagicMock(returncode=0, stdout="", stderr="")
            runner.run(spec)

        cmd = _captured_cmd(m.call_args)
        workdir_args = [a for a in cmd if a.startswith("--workdir=")]
        assert len(workdir_args) == 1
        wd_value = workdir_args[0][len("--workdir="):]
        assert Path(wd_value).is_absolute()
        assert wd_value.endswith("local")


@pytest.mark.parametrize("cwd_in,expected_endswith", [
    ("workdir/run_1", "workdir/run_1"),
    ("./local", "local"),
    ("a/b/c", "a/b/c"),
])
def test_workdir_and_tmpfs_match(cwd_in: str, expected_endswith: str) -> None:
    """--workdir와 --tmpfs path가 동일한 절대경로여야 함 (tmpfs mount = workdir)."""
    runner = _make_runner_no_init()
    spec = RunSpec(cmd=["echo", "hi"], cwd=cwd_in)

    with patch("ipe.sandbox.docker_runner.subprocess.run") as m:
        m.return_value = MagicMock(returncode=0, stdout="", stderr="")
        runner.run(spec)

    cmd = _captured_cmd(m.call_args)
    workdir = next(a[len("--workdir="):] for a in cmd if a.startswith("--workdir="))
    tmpfs_path = next(
        a[len("--tmpfs="):].split(":", 1)[0] for a in cmd if a.startswith("--tmpfs=")
    )
    assert workdir == tmpfs_path, "--workdir and --tmpfs path must match"
    assert workdir.endswith(expected_endswith)
    assert Path(workdir).is_absolute()
