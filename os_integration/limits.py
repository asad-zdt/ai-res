"""Platform-neutral resource limit values."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    """CPU allowance in cores and memory ceiling in megabytes."""

    cpu_cores: float
    memory_mb: float
