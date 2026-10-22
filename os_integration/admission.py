"""Admission policy for predicted application resource demand."""

import os
from dataclasses import dataclass
from typing import Any

import psutil

from config import CPU_MARGIN, RAM_MARGIN, RESERVE_RAM_MB
from os_integration.limits import Limits
from os_integration.priority import choose_niceness


@dataclass(frozen=True)
class AdmissionDecision:
    """Admission outcome, explanatory reason, and proposed enforcement limits."""

    admitted: bool
    reason: str | None
    limits: Limits | None
    niceness: int


def _system_snapshot() -> dict[str, float | int]:
    """Read RAM, logical CPU count, and recent CPU utilization from psutil."""
    memory = psutil.virtual_memory()
    logical_cores = psutil.cpu_count(logical=True)
    if logical_cores is None:
        raise RuntimeError("Unable to determine the logical CPU count")
    return {
        "total_ram_mb": memory.total / (1024 * 1024),
        "available_ram_mb": memory.available / (1024 * 1024),
        "logical_cores": logical_cores,
        "recent_cpu_pct": psutil.cpu_percent(interval=1),
    }


def _limits_for(
    predicted: dict[str, float],
    snapshot: dict[str, Any],
) -> Limits:
    """Calculate bounded CPU and committed-memory limits from a prediction."""
    logical_cores = int(snapshot["logical_cores"])
    cpu_cores = max(
        0.25,
        min(
            float(logical_cores),
            float(predicted["cpu_pct"]) / 100.0 * CPU_MARGIN,
        ),
    )
    memory_mb = max(128.0, float(predicted["ram_mb"]) * RAM_MARGIN)
    return Limits(cpu_cores=cpu_cores, memory_mb=memory_mb)


def _reserve_ram_mb() -> float:
    """Read the RAM reserve override or fall back to the configured default."""
    raw_value = os.getenv("RESERVE_RAM_MB")
    if raw_value is None:
        return RESERVE_RAM_MB
    try:
        reserve_mb = float(raw_value)
    except ValueError as error:
        raise ValueError("RESERVE_RAM_MB must be a non-negative number") from error
    if reserve_mb < 0:
        raise ValueError("RESERVE_RAM_MB must be a non-negative number")
    return reserve_mb


def decide(
    predicted: dict[str, float],
    snapshot: dict[str, Any] | None = None,
) -> AdmissionDecision:
    """Decide whether predicted demand fits current RAM and CPU headroom."""
    system = _system_snapshot() if snapshot is None else snapshot
    niceness = choose_niceness(predicted)
    limits = _limits_for(predicted, system)

    available_ram_mb = float(system["available_ram_mb"])
    required_ram_mb = float(predicted["ram_mb"]) * RAM_MARGIN
    remaining_ram_mb = available_ram_mb - _reserve_ram_mb()
    if required_ram_mb > remaining_ram_mb:
        reason = (
            f"Predicted RAM with margin ({required_ram_mb:.2f} MB) exceeds "
            f"available RAM after reserve ({remaining_ram_mb:.2f} MB)."
        )
        if os.getenv("ENFORCEMENT", "").strip().lower() == "off":
            return AdmissionDecision(True, None, limits, niceness)
        return AdmissionDecision(False, reason, None, niceness)

    recent_cpu_pct = float(system["recent_cpu_pct"])
    predicted_cpu_pct = float(predicted["cpu_pct"])
    if recent_cpu_pct > 90 and predicted_cpu_pct >= 100:
        reason = (
            f"Recent CPU utilization is {recent_cpu_pct:.2f}% and predicted "
            f"CPU demand is {predicted_cpu_pct:.2f}%."
        )
        if os.getenv("ENFORCEMENT", "").strip().lower() == "off":
            return AdmissionDecision(True, None, limits, niceness)
        return AdmissionDecision(False, reason, None, niceness)

    return AdmissionDecision(True, None, limits, niceness)
