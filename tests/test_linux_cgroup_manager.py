"""Tests for Linux cgroups v2 resource management."""

from pathlib import Path

import pytest

from os_integration.job_manager import Limits
from os_integration.linux_cgroup_manager import (
    LinuxCgroupManager,
    LinuxCgroupUnavailable,
)


class FakeCgroupManager(LinuxCgroupManager):
    """Use regular files to simulate the cgroup v2 control-file interface."""

    @staticmethod
    def _create_group_directory(path: Path) -> None:
        path.mkdir()
        for name in (
            "cpu.max",
            "memory.max",
            "cgroup.procs",
            "cpu.stat",
            "memory.events",
            "memory.current",
            "memory.peak",
        ):
            (path / name).touch()

    @staticmethod
    def _remove_group_directory(path: Path) -> None:
        for control_file in path.iterdir():
            control_file.unlink()
        path.rmdir()


def _manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeCgroupManager:
    """Create a fake manager with cgroup v2 availability enabled."""
    monkeypatch.setattr("os_integration.linux_cgroup_manager.sys.platform", "linux")
    base = tmp_path / "delegated"
    base.mkdir()
    (base / "cgroup.controllers").write_text("cpu memory", encoding="ascii")
    (base / "cgroup.subtree_control").write_text("cpu memory", encoding="ascii")
    manager = FakeCgroupManager(base_path=base)
    monkeypatch.setattr(manager, "_is_cgroup_v2_mount", lambda: True)
    return manager


def test_is_available_requires_v2_controllers_and_writable_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path, monkeypatch)

    assert manager.is_available()

    (manager.base_path / "cgroup.subtree_control").write_text(
        "memory",
        encoding="ascii",
    )
    assert not manager.is_available()


def test_is_unavailable_on_non_linux_platform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path, monkeypatch)
    monkeypatch.setattr("os_integration.linux_cgroup_manager.sys.platform", "win32")

    assert not manager.is_available()


def test_create_writes_cpu_quota_and_memory_max(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path, monkeypatch)

    handle = Path(manager.create(Limits(cpu_cores=0.5, memory_mb=256)))

    assert handle.parent == manager.base_path
    assert (handle / "cpu.max").read_text(encoding="ascii") == "50000 100000"
    assert (handle / "memory.max").read_text(encoding="ascii") == str(
        256 * 1024 * 1024
    )


def test_attach_and_usage_read_cgroup_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path, monkeypatch)
    handle = Path(manager.create(Limits(cpu_cores=1, memory_mb=128)))
    (handle / "cpu.stat").write_text("usage_usec 3000000\n", encoding="ascii")
    (handle / "memory.events").write_text(
        "low 0\nhigh 0\nmax 1\noom 0\noom_kill 0\n",
        encoding="ascii",
    )
    (handle / "memory.peak").write_text(str(64 * 1024 * 1024), encoding="ascii")
    (handle / "memory.max").write_text(str(128 * 1024 * 1024), encoding="ascii")

    manager.attach(handle, 12345)
    usage = manager.usage(handle)

    assert (handle / "cgroup.procs").read_text(encoding="ascii") == "12345"
    assert usage["cpu_seconds"] == 3
    assert usage["peak_memory_mb"] == 64
    assert usage["limit_reached"] is True


def test_cleanup_removes_empty_run_cgroup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path, monkeypatch)
    handle = Path(manager.create(Limits(cpu_cores=1, memory_mb=128)))

    manager.cleanup(handle)

    assert not handle.exists()


def test_create_refuses_when_cgroups_are_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path, monkeypatch)
    monkeypatch.setattr(manager, "_is_cgroup_v2_mount", lambda: False)

    with pytest.raises(LinuxCgroupUnavailable, match="unavailable"):
        manager.create(Limits(cpu_cores=1, memory_mb=128))


def test_create_permission_failure_is_reported_for_priority_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path, monkeypatch)

    def deny_group_creation(path: Path) -> None:
        raise PermissionError("permission denied")

    monkeypatch.setattr(manager, "_create_group_directory", deny_group_creation)

    with pytest.raises(LinuxCgroupUnavailable, match="permission denied"):
        manager.create(Limits(cpu_cores=1, memory_mb=128))
