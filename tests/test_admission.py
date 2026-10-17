"""Tests for resource admission decisions."""

from typing import Any

import pytest

from os_integration.admission import decide
from os_integration.job_manager import Limits

_ROOMY_SNAPSHOT: dict[str, Any] = {
    "total_ram_mb": 16_384.0,
    "available_ram_mb": 12_288.0,
    "logical_cores": 8,
    "recent_cpu_pct": 20.0,
}


def test_plenty_of_ram_admits_with_expected_limits() -> None:
    """An affordable app is admitted with calculated CPU and memory limits."""
    decision = decide({"cpu_pct": 50.0, "ram_mb": 1000.0}, _ROOMY_SNAPSHOT)

    assert decision.admitted is True
    assert decision.reason is None
    assert decision.limits == Limits(cpu_cores=0.75, memory_mb=2000.0)
    assert decision.niceness == 0


def test_low_ram_refuses_with_required_and_available_values() -> None:
    """A prediction above RAM headroom is rejected with both quantities."""
    snapshot = {**_ROOMY_SNAPSHOT, "available_ram_mb": 1500.0}

    decision = decide({"cpu_pct": 30.0, "ram_mb": 500.0}, snapshot)

    assert decision.admitted is False
    assert decision.limits is None
    assert "1000.00 MB" in (decision.reason or "")
    assert "476.00 MB" in (decision.reason or "")


def test_busy_cpu_refuses_heavy_app() -> None:
    """High current CPU utilization blocks a predicted 100%-plus app."""
    snapshot = {**_ROOMY_SNAPSHOT, "recent_cpu_pct": 95.0}

    decision = decide({"cpu_pct": 120.0, "ram_mb": 100.0}, snapshot)

    assert decision.admitted is False
    assert decision.reason is not None
    assert "95.00%" in decision.reason
    assert "120.00%" in decision.reason


def test_light_app_is_admitted_on_busy_cpu() -> None:
    """A light CPU prediction remains admissible during high utilization."""
    snapshot = {**_ROOMY_SNAPSHOT, "recent_cpu_pct": 95.0}

    decision = decide({"cpu_pct": 30.0, "ram_mb": 100.0}, snapshot)

    assert decision.admitted is True
    assert decision.limits is not None


def test_exact_ram_and_cpu_admission_thresholds_are_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Treat equality at both refusal thresholds as admissible."""
    monkeypatch.delenv("ENFORCEMENT", raising=False)
    monkeypatch.delenv("RESERVE_RAM_MB", raising=False)
    snapshot = {
        **_ROOMY_SNAPSHOT,
        "available_ram_mb": 1024.0 + 1000.0,
        "recent_cpu_pct": 90.0,
    }

    decision = decide({"cpu_pct": 100.0, "ram_mb": 500.0}, snapshot)

    assert decision.admitted is True
    assert decision.limits is not None


def test_cpu_threshold_refuses_only_above_ninety_percent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a 100% CPU prediction once recent utilization exceeds 90%."""
    monkeypatch.delenv("ENFORCEMENT", raising=False)
    snapshot = {**_ROOMY_SNAPSHOT, "recent_cpu_pct": 90.01}

    decision = decide({"cpu_pct": 100.0, "ram_mb": 100.0}, snapshot)

    assert decision.admitted is False
    assert decision.limits is None


def test_enforcement_off_admits_ram_overcommit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabling enforcement permits RAM overcommit while retaining limits."""
    monkeypatch.setenv("ENFORCEMENT", "off")
    snapshot = {**_ROOMY_SNAPSHOT, "available_ram_mb": 1500.0}

    decision = decide({"cpu_pct": 50.0, "ram_mb": 1000.0}, snapshot)

    assert decision.admitted is True
    assert decision.reason is None
    assert decision.limits == Limits(cpu_cores=0.75, memory_mb=2000.0)


def test_ram_reserve_can_be_overridden_by_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Honor the configured reserve override for API admission checks."""
    monkeypatch.setenv("RESERVE_RAM_MB", "100000")

    decision = decide({"cpu_pct": 30.0, "ram_mb": 100.0}, _ROOMY_SNAPSHOT)

    assert decision.admitted is False
    assert decision.reason is not None
    assert "-87712.00 MB" in decision.reason
