"""Select the resource-enforcement backend for the current operating system."""

import sys
from typing import Protocol

from os_integration.job_manager import JobManager, Limits
from os_integration.linux_cgroup_manager import LinuxCgroupManager


class EnforcementManager(Protocol):
    """Operations shared by Windows Job Objects and Linux cgroups v2."""

    def is_available(self) -> bool:
        """Return whether resource limits can be applied on this host."""

    def create(self, limits: Limits) -> object:
        """Create a limited process group and return its handle."""

    def attach(self, handle: object, pid: int) -> None:
        """Attach a process to the limited process group."""

    def usage(self, handle: object) -> dict[str, float | int | bool]:
        """Return resource usage and limit status."""

    def cleanup(self, handle: object) -> None:
        """Stop remaining group processes and release the group."""


def create_enforcement_manager() -> EnforcementManager:
    """Return the native resource-enforcement manager for this platform."""
    if sys.platform == "win32":
        return JobManager()
    if sys.platform == "linux":
        return LinuxCgroupManager()
    raise RuntimeError(f"Unsupported operating system for enforcement: {sys.platform}")
