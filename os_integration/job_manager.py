"""Windows Job Object resource limits for spawned process groups."""

import ctypes
import os
import sys
from contextlib import contextmanager
from typing import Iterator

import psutil

from os_integration.limits import Limits


class JobUnavailable(RuntimeError):
    """Raised when Windows Job Object functionality is unavailable."""


class _CpuRateControlInformation(ctypes.Structure):
    """Windows JOBOBJECT_CPU_RATE_CONTROL_INFORMATION layout."""

    _fields_ = [
        ("ControlFlags", ctypes.c_uint32),
        ("CpuRate", ctypes.c_uint32),
    ]


def cpu_rate_for_cores(cpu_cores: float, logical_cores: int) -> int:
    """Convert a CPU core allowance to the Windows 1/100-percent job unit."""
    if cpu_cores <= 0 or logical_cores <= 0:
        raise ValueError("cpu_cores and logical_cores must be greater than zero")
    return max(1, min(10000, round(cpu_cores / logical_cores * 10000)))


def _imports() -> tuple[object, object, object]:
    """Load pywin32 modules or raise an actionable availability error."""
    try:
        import win32api
        import win32con
        import win32job
    except ImportError as error:
        raise JobUnavailable(
            "Windows Job Objects require pywin32; run `pip install pywin32`."
        ) from error
    return win32job, win32api, win32con


def _set_cpu_limit(handle: object, cpu_cores: float) -> None:
    """Set a hard CPU cap using pywin32 or the native kernel32 API."""
    logical_cores = psutil.cpu_count(logical=True)
    if logical_cores is None:
        raise JobUnavailable("Unable to determine the number of logical CPU cores")
    cpu_rate = cpu_rate_for_cores(cpu_cores, logical_cores)
    win32job, _, _ = _imports()
    information_class = getattr(
        win32job,
        "JobObjectCpuRateControlInformation",
        15,
    )
    control_enable = getattr(win32job, "JOB_OBJECT_CPU_RATE_CONTROL_ENABLE", 0x1)
    control_hard_cap = getattr(win32job, "JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP", 0x4)
    information = {
        "ControlFlags": control_enable | control_hard_cap,
        "CpuRate": cpu_rate,
    }
    try:
        win32job.SetInformationJobObject(handle, information_class, information)
        return
    except (AttributeError, TypeError, NotImplementedError):
        pass
    except Exception as error:
        if getattr(error, "winerror", None) not in {87, 120}:
            raise JobUnavailable(f"Could not set the Job Object CPU limit: {error}") from error

    native_information = _CpuRateControlInformation(
        control_enable | control_hard_cap,
        cpu_rate,
    )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_information = kernel32.SetInformationJobObject
    set_information.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    set_information.restype = ctypes.c_int
    succeeded = set_information(
        int(handle),
        information_class,
        ctypes.byref(native_information),
        ctypes.sizeof(native_information),
    )
    if not succeeded:
        error_code = ctypes.get_last_error()
        raise JobUnavailable(
            f"Could not set the Job Object CPU limit (Windows error {error_code})."
        )


class JobManager:
    """Create and manage Windows Job Objects for spawned processes."""

    def is_available(self) -> bool:
        """Return whether this process can create a Windows Job Object."""
        if sys.platform != "win32":
            return False
        try:
            win32job, win32api, _ = _imports()
            handle = win32job.CreateJobObject(None, "")
            win32api.CloseHandle(handle)
            return True
        except Exception:
            return False

    def create(self, limits: Limits) -> object:
        """Create an unnamed Job Object with CPU and committed-memory limits."""
        if sys.platform != "win32":
            raise JobUnavailable("Job Objects require Windows 10 or later.")
        if limits.cpu_cores <= 0 or limits.memory_mb <= 0:
            raise ValueError("CPU and memory limits must be greater than zero")

        win32job, win32api, _ = _imports()
        handle = None
        try:
            handle = win32job.CreateJobObject(None, "")
            extended_class = win32job.JobObjectExtendedLimitInformation
            limit_flags = (
                win32job.JOB_OBJECT_LIMIT_JOB_MEMORY
                | win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            extended_info = win32job.QueryInformationJobObject(
                handle,
                extended_class,
            )
            extended_info["BasicLimitInformation"]["LimitFlags"] = limit_flags
            extended_info["JobMemoryLimit"] = int(limits.memory_mb * 1024 * 1024)
            # JobMemoryLimit counts committed memory, typically more than RSS.
            # Allocations fail at the cap; applications commonly exit/crash
            # rather than being terminated by the OS OOM killer.
            win32job.SetInformationJobObject(
                handle,
                extended_class,
                extended_info,
            )
            _set_cpu_limit(handle, limits.cpu_cores)
            return handle
        except JobUnavailable:
            if handle is not None:
                win32api.CloseHandle(handle)
            raise
        except Exception as error:
            if handle is not None:
                try:
                    self.cleanup(handle)
                except Exception:
                    win32api.CloseHandle(handle)
            message = str(error)
            if "winerror 87" in message.lower() or "not supported" in message.lower():
                raise JobUnavailable(
                    "This Job Object feature needs Windows 10 or later."
                ) from error
            raise JobUnavailable(f"Could not create a resource-limited Job Object: {error}") from error

    def attach(self, handle: object, pid: int) -> None:
        """Attach a spawned process to a job and verify membership."""
        _validate_pid(pid)
        win32job, win32api, win32con = _imports()
        process_handle = None
        query_handle = None
        try:
            access = win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE
            process_handle = win32api.OpenProcess(access, False, pid)
            win32job.AssignProcessToJobObject(handle, process_handle)
            query_access = getattr(
                win32con,
                "PROCESS_QUERY_LIMITED_INFORMATION",
                win32con.PROCESS_QUERY_INFORMATION,
            )
            query_handle = win32api.OpenProcess(query_access, False, pid)
            if not win32job.IsProcessInJob(query_handle, handle):
                raise JobUnavailable(
                    f"Process {pid} was not assigned to the requested Job Object."
                )
        except JobUnavailable:
            raise
        except Exception as error:
            raise JobUnavailable(
                f"Could not attach spawned process {pid} to its Job Object: {error}"
            ) from error
        finally:
            if process_handle is not None:
                win32api.CloseHandle(process_handle)
            if query_handle is not None:
                win32api.CloseHandle(query_handle)

    def usage(self, handle: object) -> dict[str, float | int | bool]:
        """Return aggregate CPU, process count, peak memory, and limit status."""
        win32job, _, _ = _imports()
        try:
            accounting_class = win32job.JobObjectBasicAccountingInformation
            accounting = win32job.QueryInformationJobObject(handle, accounting_class)
            extended_class = win32job.JobObjectExtendedLimitInformation
            extended = win32job.QueryInformationJobObject(handle, extended_class)
            peak_bytes = int(extended.get("PeakJobMemoryUsed", 0))
            memory_limit = int(extended.get("JobMemoryLimit", 0))
            total_cpu_100ns = int(accounting.get("TotalUserTime", 0)) + int(
                accounting.get("TotalKernelTime", 0)
            )
            return {
                "cpu_seconds": total_cpu_100ns / 10_000_000,
                "active_processes": int(accounting.get("ActiveProcesses", 0)),
                "peak_memory_mb": peak_bytes / (1024 * 1024),
                "limit_reached": bool(
                    memory_limit > 0 and peak_bytes >= memory_limit * 0.95
                ),
            }
        except Exception as error:
            raise JobUnavailable(f"Could not query Job Object usage: {error}") from error

    def cleanup(self, handle: object) -> None:
        """Terminate all job processes and close the Job Object handle."""
        if handle is None:
            return
        try:
            win32job, win32api, _ = _imports()
        except JobUnavailable:
            return
        try:
            win32job.TerminateJobObject(handle, 1)
        except Exception:
            pass
        try:
            win32api.CloseHandle(handle)
        except Exception:
            pass

    @contextmanager
    def run_group(self, limits: Limits) -> Iterator[object]:
        """Yield a limited Job Object handle and always clean it up afterward."""
        handle = self.create(limits)
        try:
            yield handle
        finally:
            self.cleanup(handle)


def _validate_pid(pid: int) -> None:
    """Reject system-reserved PIDs and this process before touching a target."""
    if pid <= 4:
        raise ValueError("PID must be greater than 4")
    if pid == os.getpid():
        raise ValueError("Refusing to manage the current process")
