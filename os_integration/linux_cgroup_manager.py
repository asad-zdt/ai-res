"""Linux cgroups v2 resource limits for application process groups."""

import os
import re
import sys
import uuid
from pathlib import Path

import psutil

from os_integration.limits import Limits

_CGROUP_NAME_PATTERN = re.compile(r"^run-[0-9a-f]{32}$")
_PROCESS_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
)
_CGROUP_CONTROLLERS = {"cpu", "memory"}


class LinuxCgroupUnavailable(RuntimeError):
    """Raised when a cgroups v2 operation cannot be completed."""


class LinuxCgroupCleanupError(LinuxCgroupUnavailable):
    """Raised when failed setup leaves a cgroup that could not be removed."""


class LinuxCgroupManager:
    """Create and manage per-run cgroups below a delegated v2 subtree."""

    def __init__(
        self,
        base_path: Path | None = None,
        mountinfo_path: Path = Path("/proc/self/mountinfo"),
    ) -> None:
        """Initialize the delegated cgroup path and mount table location."""
        configured_path = os.getenv(
            "AI_RES_CGROUP_ROOT",
            "/sys/fs/cgroup/ai-resource-engine",
        )
        self.base_path = (
            base_path if base_path is not None else Path(configured_path)
        ).resolve()
        self.mountinfo_path = mountinfo_path

    def is_available(self) -> bool:
        """Return whether a writable cgroups v2 subtree has required controllers."""
        if sys.platform != "linux":
            return False
        if not self._is_cgroup_v2_mount() or not self.base_path.is_dir():
            return False
        controllers_path = self.base_path / "cgroup.controllers"
        subtree_path = self.base_path / "cgroup.subtree_control"
        try:
            available = set(controllers_path.read_text(encoding="ascii").split())
            enabled = set(subtree_path.read_text(encoding="ascii").split())
        except (OSError, UnicodeError):
            return False
        return (
            _CGROUP_CONTROLLERS <= available
            and _CGROUP_CONTROLLERS <= enabled
            and os.access(self.base_path, os.W_OK)
        )

    def create(self, limits: Limits) -> object:
        """Create a uniquely named cgroup and apply CPU and memory limits."""
        if not self.is_available():
            raise LinuxCgroupUnavailable(
                "A writable Linux cgroups v2 subtree with cpu and memory "
                "controllers is unavailable."
            )
        if limits.cpu_cores <= 0 or limits.memory_mb <= 0:
            raise ValueError("CPU and memory limits must be greater than zero")

        path = self.base_path / f"run-{uuid.uuid4().hex}"
        try:
            self._create_group_directory(path)
            period_us = 100_000
            quota_us = max(1, round(limits.cpu_cores * period_us))
            self._write_control(path / "cpu.max", f"{quota_us} {period_us}")
            memory_bytes = max(1, round(limits.memory_mb * 1024 * 1024))
            self._write_control(path / "memory.max", str(memory_bytes))
        except OSError as error:
            if path.exists():
                try:
                    self._remove_group_directory(path)
                except OSError as cleanup_error:
                    raise LinuxCgroupCleanupError(
                        "Could not configure the Linux cgroup and could not remove "
                        f"the partial cgroup {path}: {cleanup_error}"
                    ) from error
            raise LinuxCgroupUnavailable(
                f"Could not create or configure a Linux cgroup: {error}"
            ) from error
        return path

    def attach(self, handle: object, pid: int) -> None:
        """Move a spawned process into its run cgroup."""
        _validate_pid(pid)
        path = self._validated_path(handle)
        try:
            self._write_control(path / "cgroup.procs", str(pid))
        except OSError as error:
            raise LinuxCgroupUnavailable(
                f"Could not attach process {pid} to its Linux cgroup: {error}"
            ) from error

    def usage(self, handle: object) -> dict[str, float | int | bool]:
        """Read CPU and memory usage and report whether the memory cap was hit."""
        path = self._validated_path(handle)
        try:
            cpu_stats = _read_key_values(path / "cpu.stat")
            memory_events = _read_key_values(path / "memory.events")
            memory_peak_path = path / "memory.peak"
            memory_path = (
                memory_peak_path
                if memory_peak_path.is_file()
                else path / "memory.current"
            )
            peak_bytes = int(memory_path.read_text(encoding="ascii").strip())
            memory_limit = int((path / "memory.max").read_text(encoding="ascii"))
            process_ids = _read_process_ids(path / "cgroup.procs")
        except (OSError, ValueError) as error:
            raise LinuxCgroupUnavailable(
                f"Could not read Linux cgroup usage: {error}"
            ) from error

        return {
            "cpu_seconds": int(cpu_stats.get("usage_usec", 0)) / 1_000_000,
            "active_processes": len(process_ids),
            "peak_memory_mb": peak_bytes / (1024 * 1024),
            "limit_reached": (
                int(memory_events.get("max", 0)) > 0
                or int(memory_events.get("oom", 0)) > 0
                or int(memory_events.get("oom_kill", 0)) > 0
                or peak_bytes >= memory_limit
            ),
        }

    def cleanup(self, handle: object) -> None:
        """Stop remaining cgroup members and remove the per-run cgroup."""
        path = self._validated_path(handle)
        try:
            process_ids = _read_process_ids(path / "cgroup.procs")
        except (OSError, ValueError) as error:
            raise LinuxCgroupUnavailable(
                f"Could not inspect Linux cgroup members: {error}"
            ) from error

        processes: list[psutil.Process] = []
        for pid in process_ids:
            _validate_pid(pid)
            try:
                processes.append(psutil.Process(pid))
            except _PROCESS_ERRORS:
                continue

        for process in processes:
            try:
                process.terminate()
            except _PROCESS_ERRORS:
                continue
        _, survivors = psutil.wait_procs(processes, timeout=2)
        for process in survivors:
            try:
                process.kill()
            except _PROCESS_ERRORS:
                continue
        if survivors:
            psutil.wait_procs(survivors, timeout=2)

        try:
            self._remove_group_directory(path)
        except OSError as error:
            raise LinuxCgroupUnavailable(
                f"Could not remove Linux cgroup {path}: {error}"
            ) from error

    def _validated_path(self, handle: object) -> Path:
        """Ensure a handle names only a generated direct child of the base."""
        if not isinstance(handle, (str, Path)):
            raise ValueError("Invalid Linux cgroup handle")
        path = Path(handle).resolve()
        if (
            path.parent != self.base_path
            or _CGROUP_NAME_PATTERN.fullmatch(path.name) is None
        ):
            raise ValueError("Invalid Linux cgroup handle")
        return path

    def _is_cgroup_v2_mount(self) -> bool:
        """Check that the configured base path lies on a cgroups v2 mount."""
        try:
            mountinfo = self.mountinfo_path.read_text(encoding="utf-8")
        except OSError:
            return False

        for line in mountinfo.splitlines():
            fields = line.split()
            if len(fields) < 6 or "-" not in fields:
                continue
            separator = fields.index("-")
            if separator + 1 >= len(fields) or fields[separator + 1] != "cgroup2":
                continue
            mountpoint = Path(fields[4].replace("\\040", " ")).resolve()
            if self.base_path == mountpoint or mountpoint in self.base_path.parents:
                return True
        return False

    @staticmethod
    def _write_control(path: Path, value: str) -> None:
        """Write one value to a cgroup control file."""
        with path.open("w", encoding="ascii") as control_file:
            control_file.write(value)

    @staticmethod
    def _create_group_directory(path: Path) -> None:
        """Create one cgroup directory; control files are kernel-provided."""
        path.mkdir()

    @staticmethod
    def _remove_group_directory(path: Path) -> None:
        """Remove an empty cgroup directory."""
        path.rmdir()


def _read_key_values(path: Path) -> dict[str, int]:
    """Parse the whitespace-delimited key/value format used by cgroup stats."""
    values: dict[str, int] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        key, value = line.split(maxsplit=1)
        values[key] = int(value)
    return values


def _read_process_ids(path: Path) -> list[int]:
    """Read process IDs from a cgroup.procs file."""
    return [int(value) for value in path.read_text(encoding="ascii").split()]


def _validate_pid(pid: int) -> None:
    """Reject system-reserved process IDs and this process."""
    if pid <= 4:
        raise ValueError("PID must be greater than 4")
    if pid == os.getpid():
        raise ValueError("Refusing to manage the current process")


if __name__ == "__main__":
    manager = LinuxCgroupManager()
    print(
        {
            "platform": sys.platform,
            "cgroups_v2_available": manager.is_available(),
            "base_path": str(manager.base_path),
        }
    )
