"""Tests for process-tree resource monitoring."""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

import collector.monitor as monitor_module
from collector.monitor import Sample, monitor_process, summarize


def test_monitor_samples_cpu_and_peak_memory() -> None:
    """Sample a child that uses about 200 MB and burns CPU for four seconds."""
    code = (
        "import time\n"
        "data = bytearray(200 * 1024 * 1024)\n"
        "for i in range(0, len(data), 4096): data[i] = 1\n"
        "deadline = time.monotonic() + 4\n"
        "value = 0\n"
        "while time.monotonic() < deadline:\n"
        "    value = (value + 1) % 1000003\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    samples = monitor_process(process)
    result = summarize(samples)

    assert len(samples) >= 3
    assert result["ram_mb"] >= 140
    assert result["cpu_pct"] > 20
    assert samples.timed_out is False


def test_monitor_timeout_kills_process() -> None:
    """Timeout marks samples and terminates the monitored process."""
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    samples = monitor_process(process, interval_s=0.05, timeout_s=0.2)

    assert samples.timed_out is True
    assert process.poll() is not None


def test_monitor_records_final_sample_for_already_exited_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return one final sample when poll already reports that the process exited."""
    monkeypatch.setattr(
        monitor_module,
        "_tree_processes",
        lambda root, processes: {},
    )
    monkeypatch.setattr(
        monitor_module,
        "_sample_processes",
        lambda current, processes, io_totals: (0.0, 0.0, 0),
    )
    monkeypatch.setattr(monitor_module, "_system_network_bytes", lambda: None)
    process = SimpleNamespace(pid=os.getpid(), poll=lambda: 0)

    samples = monitor_process(process)

    assert len(samples) == 1
    assert samples.timed_out is False
    assert summarize(samples) == {
        "cpu_pct": 0.0,
        "ram_mb": 0.0,
        "disk_mbps": 0.0,
        "net_kbps": 0.0,
    }


def test_summarize_uses_mean_rates_and_peak_ram() -> None:
    """Aggregate samples using their specified mean and peak definitions."""
    samples = [
        Sample(0.0, 10.0, 100.0, 1.0, 2.0),
        Sample(1.0, 30.0, 200.0, 3.0, 4.0),
    ]

    assert summarize(samples) == {
        "cpu_pct": 20.0,
        "ram_mb": 200.0,
        "disk_mbps": 2.0,
        "net_kbps": 3.0,
    }


def test_summarize_rejects_empty_samples() -> None:
    """An empty sample list cannot produce meaningful metrics."""
    with pytest.raises(ValueError, match="empty sample list"):
        summarize([])
