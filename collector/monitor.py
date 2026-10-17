"""Sample process-tree resource usage with psutil.

On Windows, per-process I/O counters include all process I/O (files, pipes,
network, devices), not only disk traffic, so disk_mbps can overstate real disk
traffic for applications that also use the network. Network counters are
system-wide because psutil does not expose per-process network counters.
"""

import subprocess
import sys
import time
from dataclasses import dataclass

import psutil

_PROCESS_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
)
_BYTES_PER_MB = 1024 * 1024
_BYTES_PER_KB = 1024


@dataclass
class Sample:
    """One sample of process-tree and system-wide resource usage."""

    t_s: float
    cpu_pct: float
    rss_mb: float
    disk_mbps: float
    net_kbps: float


class MonitorSamples(list[Sample]):
    """Sample list that also records whether the monitored run timed out."""

    def __init__(self) -> None:
        """Initialize samples and their timeout status."""
        super().__init__()
        self.timed_out = False


def _tree_processes(
    root: psutil.Process,
    processes: dict[int, psutil.Process],
) -> dict[int, psutil.Process]:
    """Discover the live process tree and retain Process objects by PID."""
    current: dict[int, psutil.Process] = {}
    try:
        descendants = root.children(recursive=True)
    except _PROCESS_ERRORS:
        descendants = []

    for process in (root, *descendants):
        try:
            if process.is_running():
                retained = processes.setdefault(process.pid, process)
                current[process.pid] = retained
        except _PROCESS_ERRORS:
            continue
    return current


def _counter_snapshot(
    process: psutil.Process,
) -> tuple[int, int] | None:
    """Read cumulative process I/O counters when the process permits access."""
    try:
        counters = process.io_counters()
        return counters.read_bytes, counters.write_bytes
    except _PROCESS_ERRORS:
        return None


def _system_network_bytes() -> int | None:
    """Read cumulative system-wide sent and received network bytes."""
    try:
        counters = psutil.net_io_counters()
    except _PROCESS_ERRORS:
        return None
    if counters is None:
        return None
    return counters.bytes_sent + counters.bytes_recv


def _sample_processes(
    current: dict[int, psutil.Process],
    processes: dict[int, psutil.Process],
    io_totals: dict[int, tuple[int, int]],
) -> tuple[float, float, int]:
    """Collect CPU, resident memory, and process-tree I/O counter deltas."""
    cpu_pct = 0.0
    rss_bytes = 0
    io_delta_bytes = 0

    for pid, process in current.items():
        try:
            cpu_pct += process.cpu_percent(interval=None)
        except _PROCESS_ERRORS:
            pass
        try:
            rss_bytes += process.memory_info().rss
        except _PROCESS_ERRORS:
            pass

    for pid, process in processes.items():
        totals = _counter_snapshot(process)
        if totals is None:
            continue
        previous = io_totals.get(pid)
        if previous is not None:
            io_delta_bytes += max(0, totals[0] - previous[0])
            io_delta_bytes += max(0, totals[1] - previous[1])
        io_totals[pid] = totals

    return cpu_pct, rss_bytes / _BYTES_PER_MB, io_delta_bytes


def _terminate_tree(root: psutil.Process) -> None:
    """Terminate descendants before their root, then kill remaining processes."""
    try:
        descendants = root.children(recursive=True)
    except _PROCESS_ERRORS:
        descendants = []
    ordered_processes = [*reversed(descendants), root]

    for process in ordered_processes:
        try:
            process.terminate()
        except _PROCESS_ERRORS:
            continue

    try:
        _, survivors = psutil.wait_procs(ordered_processes, timeout=3)
    except _PROCESS_ERRORS:
        survivors = []

    for process in survivors:
        try:
            process.kill()
        except _PROCESS_ERRORS:
            continue


def monitor_process(
    popen: subprocess.Popen[bytes],
    interval_s: float = 1.0,
    timeout_s: float | None = None,
) -> MonitorSamples:
    """Sample a process tree until exit or timeout, then return its samples.

    Windows process I/O counters include files, pipes, network, and device I/O,
    so ``disk_mbps`` can overstate actual disk traffic for network-heavy
    processes. ``net_kbps`` is based on system-wide counters because psutil
    does not provide per-process network counters.
    """
    if interval_s <= 0:
        raise ValueError("interval_s must be greater than zero")
    if timeout_s is not None and timeout_s < 0:
        raise ValueError("timeout_s cannot be negative")

    root = psutil.Process(popen.pid)
    samples = MonitorSamples()
    processes: dict[int, psutil.Process] = {}
    io_totals: dict[int, tuple[int, int]] = {}
    start_time = time.monotonic()
    previous_sample_time = start_time
    previous_network_bytes: int | None = None
    next_tick = start_time

    while True:
        now = time.monotonic()
        current = _tree_processes(root, processes)
        cpu_pct, rss_mb, disk_delta_bytes = _sample_processes(
            current,
            processes,
            io_totals,
        )
        network_bytes = _system_network_bytes()
        elapsed = now - previous_sample_time
        if elapsed > 0:
            disk_mbps = disk_delta_bytes / _BYTES_PER_MB / elapsed
            if network_bytes is not None and previous_network_bytes is not None:
                network_delta = max(0, network_bytes - previous_network_bytes)
                net_kbps = network_delta / _BYTES_PER_KB / elapsed
            else:
                net_kbps = 0.0
        else:
            disk_mbps = 0.0
            net_kbps = 0.0

        samples.append(
            Sample(
                t_s=now - start_time,
                cpu_pct=cpu_pct,
                rss_mb=rss_mb,
                disk_mbps=disk_mbps,
                net_kbps=net_kbps,
            )
        )
        previous_sample_time = now
        if network_bytes is not None:
            previous_network_bytes = network_bytes

        if popen.poll() is not None:
            break

        if timeout_s is not None and now - start_time >= timeout_s:
            samples.timed_out = True
            _terminate_tree(root)
            final_time = time.monotonic()
            current = _tree_processes(root, processes)
            cpu_pct, rss_mb, disk_delta_bytes = _sample_processes(
                current,
                processes,
                io_totals,
            )
            network_bytes = _system_network_bytes()
            elapsed = final_time - previous_sample_time
            disk_mbps = (
                disk_delta_bytes / _BYTES_PER_MB / elapsed if elapsed > 0 else 0.0
            )
            if (
                elapsed > 0
                and network_bytes is not None
                and previous_network_bytes is not None
            ):
                net_kbps = (
                    max(0, network_bytes - previous_network_bytes)
                    / _BYTES_PER_KB
                    / elapsed
                )
            else:
                net_kbps = 0.0
            samples.append(
                Sample(
                    t_s=final_time - start_time,
                    cpu_pct=cpu_pct,
                    rss_mb=rss_mb,
                    disk_mbps=disk_mbps,
                    net_kbps=net_kbps,
                )
            )
            break

        next_tick += interval_s
        remaining = max(0.0, next_tick - time.monotonic())
        if timeout_s is not None:
            time_until_timeout = max(0.0, timeout_s - (time.monotonic() - start_time))
            remaining = min(remaining, time_until_timeout)
        if remaining > 0:
            time.sleep(remaining)

    return samples


def summarize(samples: list[Sample]) -> dict[str, float]:
    """Summarize mean CPU/disk/network rates and peak resident memory."""
    if not samples:
        raise ValueError("cannot summarize an empty sample list")
    count = len(samples)
    return {
        "cpu_pct": sum(sample.cpu_pct for sample in samples) / count,
        "ram_mb": max(sample.rss_mb for sample in samples),
        "disk_mbps": sum(sample.disk_mbps for sample in samples) / count,
        "net_kbps": sum(sample.net_kbps for sample in samples) / count,
    }


def main() -> None:
    """Run a short CPU-and-memory demo and print its resource summary."""
    code = (
        "import time\n"
        "data = bytearray(64 * 1024 * 1024)\n"
        "for i in range(0, len(data), 4096): data[i] = 1\n"
        "deadline = time.monotonic() + 3\n"
        "value = 0\n"
        "while time.monotonic() < deadline:\n"
        "    value = (value + 1) % 1000003\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    samples = monitor_process(process, timeout_s=10)
    print(summarize(samples))


if __name__ == "__main__":
    main()
