"""Safe Windows process priority controls."""

import os

import psutil

_PROCESS_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
)


def _validate_pid(pid: int) -> None:
    """Reject system-reserved PIDs and the current process."""
    if pid <= 4:
        raise ValueError("PID must be greater than 4")
    if pid == os.getpid():
        raise ValueError("Refusing to change the current process priority")


def priority_class_for_level(level: int) -> int:
    """Map API niceness levels 0, 5, and 10 to safe Windows classes."""
    mapping = {
        0: psutil.NORMAL_PRIORITY_CLASS,
        5: psutil.BELOW_NORMAL_PRIORITY_CLASS,
        10: psutil.IDLE_PRIORITY_CLASS,
    }
    try:
        return mapping[level]
    except KeyError:
        raise ValueError("level must be one of 0, 5, or 10") from None


def set_priority(
    pid: int,
    level: int,
    include_children: bool = True,
) -> int:
    """Apply a safe priority class to a spawned process and optionally its tree.

    Child processes inherit their parent's priority class when created. Applying
    priority while the application is still suspended therefore also covers
    children it creates after resuming.
    """
    _validate_pid(pid)
    priority_class = priority_class_for_level(level)
    try:
        root = psutil.Process(pid)
    except _PROCESS_ERRORS:
        return 0

    try:
        children = root.children(recursive=True) if include_children else []
    except _PROCESS_ERRORS:
        children = []

    applied_to_root = False
    for process in [*reversed(children), root]:
        try:
            process.nice(priority_class)
            if process.pid == pid:
                applied_to_root = True
        except _PROCESS_ERRORS:
            continue
    return level if applied_to_root else 0


def choose_niceness(predicted: dict[str, float]) -> int:
    """Choose API priority level from the predicted CPU demand."""
    cpu_pct = predicted.get("cpu_pct", 0.0)
    if cpu_pct >= 150:
        return 10
    if cpu_pct >= 60:
        return 5
    return 0
