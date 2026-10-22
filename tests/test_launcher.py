"""Tests for process launch and cleanup helpers."""

import os
import sys
from pathlib import Path

import pytest

from collector.config_loader import AppSpec
from collector.launcher import cleanup, launch, resume


def _python_spec() -> AppSpec:
    """Build a simple test application that creates a marker in its temp dir."""
    return AppSpec(
        name="launcher_test",
        category="test",
        command=(sys.executable, "-c"),
        cwd=os.getcwd(),
        timeout_s=10.0,
        variants=(
            (
                "from pathlib import Path; "
                "Path(r'{tmp}').joinpath('marker.txt').write_text('ok')",
            ),
            ("print('second')",),
        ),
        exe=Path(sys.executable),
        exe_size_mb=Path(sys.executable).stat().st_size / (1024 * 1024),
    )


def test_launch_uses_variant_and_cleanup_removes_temp_directory() -> None:
    """Launch an argv-list command and clean up its process and temp directory."""
    launched = launch(_python_spec(), variant_index=0)

    assert launched.popen.wait(timeout=10) == 0
    marker = launched.tmp_dir / "marker.txt"
    assert marker.read_text(encoding="utf-8") == "ok"
    cleanup(launched)
    assert not launched.tmp_dir.exists()


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows suspended-process support required",
)
def test_resume_resumes_spawned_process(monkeypatch) -> None:
    """Resume the process ID associated with the launch handle."""
    resumed: list[bool] = []

    class FakeProcess:
        def __init__(self, pid: int) -> None:
            assert pid == 12345

        def resume(self) -> None:
            resumed.append(True)

    monkeypatch.setattr("collector.launcher.psutil.Process", FakeProcess)
    launched = type(
        "Launch",
        (),
        {"popen": type("Process", (), {"pid": 12345})(), "resume_fd": None},
    )()

    resume(launched)

    assert resumed == [True]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux launch gate required")
def test_linux_suspended_launch_waits_until_resume(tmp_path: Path) -> None:
    """A Linux suspended launch must not execute workload code before resume."""
    import time

    spec = _python_spec()
    launched = launch(spec, suspended=True)
    marker = launched.tmp_dir / "marker.txt"
    try:
        time.sleep(0.1)
        assert not marker.exists()
        resume(launched)
        assert launched.popen.wait(timeout=10) == 0
        assert marker.read_text(encoding="utf-8") == "ok"
    finally:
        cleanup(launched)
