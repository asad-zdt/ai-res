"""Tests for OS enforcement backend selection."""

import pytest

from os_integration.factory import create_enforcement_manager
from os_integration.job_manager import JobManager
from os_integration.linux_cgroup_manager import LinuxCgroupManager


def test_factory_selects_windows_job_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("os_integration.factory.sys.platform", "win32")

    assert isinstance(create_enforcement_manager(), JobManager)


def test_factory_selects_linux_cgroup_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("os_integration.factory.sys.platform", "linux")

    assert isinstance(create_enforcement_manager(), LinuxCgroupManager)


def test_factory_rejects_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("os_integration.factory.sys.platform", "darwin")

    with pytest.raises(RuntimeError, match="Unsupported operating system"):
        create_enforcement_manager()
