"""Tests for Windows process priority and Job Object integration."""

import os
import subprocess
import sys
import time
from types import SimpleNamespace

import psutil
import pytest

import os_integration.job_manager as job_manager_module
from os_integration.job_manager import (
    JobManager,
    JobUnavailable,
    Limits,
    cpu_rate_for_cores,
)
from os_integration.priority import priority_class_for_level, set_priority

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def test_cpu_cores_convert_to_clamped_job_rate() -> None:
    """Convert core fractions to the bounded Windows CPU rate scale."""
    assert cpu_rate_for_cores(0.00001, 8) == 1
    assert cpu_rate_for_cores(0.5, 8) == 625
    assert cpu_rate_for_cores(32, 8) == 10000


def test_job_create_configures_memory_and_cpu_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create a Job Object and configure its memory and CPU limits."""
    monkeypatch.setattr(job_manager_module.sys, "platform", "win32")
    handle = object()
    information = {"BasicLimitInformation": {}}
    configured: list[tuple[object, int, dict[str, object]]] = []
    win32job = SimpleNamespace(
        CreateJobObject=lambda security, name: handle,
        JobObjectExtendedLimitInformation=9,
        JOB_OBJECT_LIMIT_JOB_MEMORY=1,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE=2,
        QueryInformationJobObject=lambda job, information_class: information,
        SetInformationJobObject=lambda job, information_class, value: configured.append(
            (job, information_class, value.copy())
        ),
    )
    monkeypatch.setattr(
        job_manager_module,
        "_imports",
        lambda: (win32job, SimpleNamespace(CloseHandle=lambda job: None), None),
    )
    cpu_limits: list[tuple[object, float]] = []
    monkeypatch.setattr(
        job_manager_module,
        "_set_cpu_limit",
        lambda job, cores: cpu_limits.append((job, cores)),
    )

    result = JobManager().create(Limits(cpu_cores=0.5, memory_mb=256.0))

    assert result is handle
    assert information["BasicLimitInformation"]["LimitFlags"] == 3
    assert information["JobMemoryLimit"] == 256 * 1024 * 1024
    assert configured[0][0:2] == (handle, 9)
    assert cpu_limits == [(handle, 0.5)]


def test_job_attach_closes_process_handles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Close both process handles after successful Job Object assignment."""
    process_handles = [object(), object()]
    closed: list[object] = []
    opened: list[int] = []
    win32api = SimpleNamespace(
        OpenProcess=lambda access, inherit, pid: (
            opened.append(access) or process_handles[len(opened) - 1]
        ),
        CloseHandle=closed.append,
    )
    win32con = SimpleNamespace(
        PROCESS_SET_QUOTA=1,
        PROCESS_TERMINATE=2,
        PROCESS_QUERY_LIMITED_INFORMATION=4,
        PROCESS_QUERY_INFORMATION=8,
    )
    assignments: list[tuple[object, object]] = []
    win32job = SimpleNamespace(
        AssignProcessToJobObject=lambda job, process: assignments.append(
            (job, process)
        ),
        IsProcessInJob=lambda process, job: True,
    )
    monkeypatch.setattr(
        job_manager_module,
        "_imports",
        lambda: (win32job, win32api, win32con),
    )
    handle = object()

    JobManager().attach(handle, 12345)

    assert assignments == [(handle, process_handles[0])]
    assert closed == process_handles
    assert opened == [3, 4]


def test_job_usage_reports_accounting_and_memory_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Convert Job Object counters and detect a nearly reached memory cap."""
    win32job = SimpleNamespace(
        JobObjectBasicAccountingInformation=1,
        JobObjectExtendedLimitInformation=2,
        QueryInformationJobObject=lambda handle, information_class: (
            {
                "TotalUserTime": 20_000_000,
                "TotalKernelTime": 10_000_000,
                "ActiveProcesses": 2,
            }
            if information_class == 1
            else {
                "PeakJobMemoryUsed": 950,
                "JobMemoryLimit": 1000,
            }
        ),
    )
    monkeypatch.setattr(
        job_manager_module,
        "_imports",
        lambda: (win32job, None, None),
    )

    usage = JobManager().usage(object())

    assert usage == {
        "cpu_seconds": 3.0,
        "active_processes": 2,
        "peak_memory_mb": 950 / (1024 * 1024),
        "limit_reached": True,
    }


def test_job_cleanup_closes_handle_even_if_termination_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Close the native handle even when terminating the Job Object fails."""
    closed: list[object] = []

    def fail_termination(handle: object, exit_code: int) -> None:
        raise OSError("termination failed")

    win32job = SimpleNamespace(TerminateJobObject=fail_termination)
    win32api = SimpleNamespace(CloseHandle=closed.append)
    monkeypatch.setattr(
        job_manager_module,
        "_imports",
        lambda: (win32job, win32api, None),
    )
    handle = object()

    JobManager().cleanup(handle)

    assert closed == [handle]


def test_job_group_cleans_up_after_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run-group cleanup executes when code in the managed block raises."""
    manager = JobManager()
    handle = object()
    cleanups: list[object] = []
    monkeypatch.setattr(manager, "create", lambda limits: handle)
    monkeypatch.setattr(manager, "cleanup", cleanups.append)

    with pytest.raises(RuntimeError, match="workload failed"):
        with manager.run_group(Limits(cpu_cores=1, memory_mb=128)):
            raise RuntimeError("workload failed")

    assert cleanups == [handle]


def test_priority_levels_map_to_safe_classes() -> None:
    """Map API levels to normal, below-normal, and idle classes."""
    assert priority_class_for_level(0) == psutil.NORMAL_PRIORITY_CLASS
    assert priority_class_for_level(5) == psutil.BELOW_NORMAL_PRIORITY_CLASS
    assert priority_class_for_level(10) == psutil.IDLE_PRIORITY_CLASS
    with pytest.raises(ValueError):
        priority_class_for_level(1)


@pytest.mark.skipif(os.name != "nt", reason="Windows priority classes required")
def test_priority_is_applied_to_spawned_process() -> None:
    """Set a child process to BELOW_NORMAL priority."""
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
    )
    try:
        applied = set_priority(process.pid, 5)
        assert applied == 5
        assert psutil.Process(process.pid).nice() == psutil.BELOW_NORMAL_PRIORITY_CLASS
    finally:
        process.terminate()
        process.wait(timeout=5)


_JOB_AVAILABLE = JobManager().is_available()


def _suspended_process(code: str) -> subprocess.Popen[bytes]:
    """Start a Windows Python process before it executes its first instruction."""
    flags = (
        subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_NO_WINDOW
        | 0x00000004
    )
    return subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


@pytest.mark.skipif(not _JOB_AVAILABLE, reason="Windows Job Objects unavailable")
@pytest.mark.slow
def test_job_cpu_limit_caps_busy_processes() -> None:
    """A half-core job cap keeps its average CPU time below 80%."""
    manager = JobManager()
    process = _suspended_process(
        "import subprocess, sys\n"
        "code = 'import time; end=time.monotonic()+6; value=0\\n'\n"
        "code += 'while time.monotonic()<end: value=(value+1)%1000003\\n'\n"
        "children = [subprocess.Popen([sys.executable, '-c', code]) for _ in range(4)]\n"
        "[child.wait() for child in children]\n"
    )
    try:
        with manager.run_group(Limits(cpu_cores=0.5, memory_mb=1024)) as handle:
            manager.attach(handle, process.pid)
            psutil.Process(process.pid).resume()
            start = time.monotonic()
            while process.poll() is None:
                time.sleep(0.2)
            duration = time.monotonic() - start
            final_cpu = float(manager.usage(handle)["cpu_seconds"])
            mean_cpu_pct = final_cpu / duration * 100
            assert process.returncode == 0
            assert mean_cpu_pct < 80
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


@pytest.mark.skipif(not _JOB_AVAILABLE, reason="Windows Job Objects unavailable")
@pytest.mark.slow
def test_job_memory_limit_causes_nonzero_exit() -> None:
    """A process exceeding its committed-memory job limit exits unsuccessfully."""
    manager = JobManager()
    process = _suspended_process(
        "data = bytearray(400 * 1024 * 1024)\n"
        "for index in range(0, len(data), 4096): data[index] = 1\n"
    )
    try:
        with manager.run_group(Limits(cpu_cores=1, memory_mb=150)) as handle:
            manager.attach(handle, process.pid)
            psutil.Process(process.pid).resume()
            exit_code = process.wait(timeout=30)
        assert exit_code != 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.skipif(not _JOB_AVAILABLE, reason="Windows Job Objects unavailable")
def test_job_cleanup_terminates_process_tree(tmp_path) -> None:
    """Closing the manager's job terminates its root process and children."""
    manager = JobManager()
    child_pid_file = tmp_path / "child-pid.txt"
    process = _suspended_process(
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(child_pid_file)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    try:
        handle = manager.create(Limits(cpu_cores=1, memory_mb=1024))
        manager.attach(handle, process.pid)
        psutil.Process(process.pid).resume()
        deadline = time.monotonic() + 5
        while not child_pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert child_pid_file.exists()
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        manager.cleanup(handle)
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(process.pid).status()
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(child_pid).status()
        manager.cleanup(handle)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
