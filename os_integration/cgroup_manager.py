"""Legacy compatibility names for the Windows Job Object manager.

New code should select platform enforcement through ``factory``.
"""

from os_integration.job_manager import JobManager, JobUnavailable

CgroupManager = JobManager
CgroupUnavailable = JobUnavailable

__all__ = ["CgroupManager", "CgroupUnavailable"]
