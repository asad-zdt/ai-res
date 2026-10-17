"""Compatibility names for the original Linux cgroups v2 integration.

The Linux design used cgroups v2 files such as cpu.max, memory.max, and
cgroup.procs. On Windows, JobManager provides the equivalent process-group
resource controls.
"""

from os_integration.job_manager import JobManager, JobUnavailable

CgroupManager = JobManager
CgroupUnavailable = JobUnavailable

__all__ = ["CgroupManager", "CgroupUnavailable"]
