"""Manually demonstrate CPU, committed-memory, and priority controls."""

from __future__ import annotations

import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import psutil

from collector.config_loader import AppSpec
from collector.launcher import LaunchedApp, cleanup, launch, resume
from collector.monitor import monitor_process, summarize
from config import resolve_path
from os_integration.job_manager import JobManager, Limits
from os_integration.priority import set_priority

RUN_SECONDS = 10


@dataclass(frozen=True)
class ExperimentResult:
    """Result row for one manual resource-control experiment."""

    name: str
    observed: str
    threshold: str
    passed: bool


def _workload_spec(
    workload: str,
    arguments: tuple[str, ...],
) -> AppSpec:
    """Create a launcher spec for one repository workload and argument set."""
    script = resolve_path("collector", "workloads", f"{workload}.py")
    return AppSpec(
        name=workload,
        category="manual_demo",
        command=(sys.executable, str(script)),
        cwd=str(resolve_path()),
        timeout_s=RUN_SECONDS + 20,
        variants=(arguments,),
        exe=script,
        exe_size_mb=script.stat().st_size / (1024 * 1024),
    )


def _mean_cpu(launched: LaunchedApp, timeout_s: float) -> float:
    """Monitor a launched process tree and return its mean CPU percentage."""
    samples = monitor_process(launched.popen, timeout_s=timeout_s)
    if samples.timed_out:
        raise RuntimeError("workload exceeded its monitoring timeout")
    if launched.popen.returncode != 0:
        raise RuntimeError(
            f"workload exited with status {launched.popen.returncode}"
        )
    return summarize(samples)["cpu_pct"]


def _run_cpu_cap(manager: JobManager) -> ExperimentResult:
    """Compare an uncapped four-worker workload with a half-core job."""
    spec = _workload_spec(
        "cpu_burn",
        ("--seconds", str(RUN_SECONDS), "--workers", "4"),
    )
    uncapped: LaunchedApp | None = None
    capped: LaunchedApp | None = None
    job = None
    try:
        uncapped = launch(spec)
        uncapped_cpu = _mean_cpu(uncapped, RUN_SECONDS + 15)

        capped = launch(spec, suspended=True)
        job = manager.create(Limits(cpu_cores=0.5, memory_mb=4096))
        manager.attach(job, capped.popen.pid)
        resume(capped)
        capped_cpu = _mean_cpu(capped, RUN_SECONDS + 15)
        ratio = capped_cpu / uncapped_cpu if uncapped_cpu > 0 else float("inf")
        passed = 25 <= capped_cpu <= 75 and ratio <= 0.5
        return ExperimentResult(
            name="CPU cap",
            observed=(
                f"uncapped {uncapped_cpu:.1f}% | capped {capped_cpu:.1f}% "
                f"| capped/uncapped {ratio:.2f}"
            ),
            threshold="capped 25-75% CPU and ratio <= 0.50",
            passed=passed,
        )
    finally:
        if job is not None:
            manager.cleanup(job)
        if capped is not None:
            cleanup(capped)
        if uncapped is not None:
            cleanup(uncapped)


def _run_memory_cap(manager: JobManager) -> ExperimentResult:
    """Run a 600 MB allocation inside a 200 MB committed-memory job."""
    spec = _workload_spec(
        "mem_hog",
        ("--mb", "600", "--seconds", str(RUN_SECONDS)),
    )
    launched: LaunchedApp | None = None
    job = None
    try:
        launched = launch(spec, suspended=True)
        logical_cores = psutil.cpu_count(logical=True)
        if not logical_cores:
            raise RuntimeError("could not determine logical CPU count")
        job = manager.create(
            Limits(cpu_cores=float(logical_cores), memory_mb=200)
        )
        manager.attach(job, launched.popen.pid)
        resume(launched)
        samples = monitor_process(launched.popen, timeout_s=RUN_SECONDS + 20)
        if samples.timed_out:
            raise RuntimeError("memory workload exceeded its monitoring timeout")
        exit_code = launched.popen.poll()
        if exit_code is None:
            raise RuntimeError("memory workload did not exit before its timeout")
        usage = manager.usage(job)
        peak_mb = float(usage["peak_memory_mb"])
        limit_reached = bool(usage["limit_reached"])
        passed = exit_code != 0 and 190 <= peak_mb <= 250 and limit_reached
        return ExperimentResult(
            name="Memory cap",
            observed=(
                f"exit {exit_code} | peak {peak_mb:.1f} MB "
                f"| limit_reached={limit_reached}"
            ),
            threshold="non-zero exit and peak 190-250 MB (near the 200 MB cap)",
            passed=passed,
        )
    finally:
        if job is not None:
            manager.cleanup(job)
        if launched is not None:
            cleanup(launched)


def _run_priority() -> ExperimentResult:
    """Compare Normal and Idle CPU shares while both processes share CPU 0."""
    spec = _workload_spec(
        "cpu_burn",
        ("--seconds", str(RUN_SECONDS), "--workers", "1"),
    )
    normal: LaunchedApp | None = None
    idle: LaunchedApp | None = None
    try:
        normal = launch(spec, suspended=True)
        idle = launch(spec, suspended=True)
        normal_process = psutil.Process(normal.popen.pid)
        idle_process = psutil.Process(idle.popen.pid)
        normal_process.cpu_affinity([0])
        idle_process.cpu_affinity([0])
        set_priority(normal.popen.pid, 0)
        set_priority(idle.popen.pid, 10)

        start_time = time.monotonic()
        resume(normal)
        resume(idle)
        with ThreadPoolExecutor(max_workers=2) as executor:
            normal_future = executor.submit(
                _mean_cpu,
                normal,
                RUN_SECONDS + 15,
            )
            idle_future = executor.submit(
                _mean_cpu,
                idle,
                RUN_SECONDS + 15,
            )
            normal_cpu = normal_future.result()
            idle_cpu = idle_future.result()
        elapsed = time.monotonic() - start_time
        total_cpu = normal_cpu + idle_cpu
        normal_share = 100 * normal_cpu / total_cpu if total_cpu > 0 else 0.0
        idle_share = 100 * idle_cpu / total_cpu if total_cpu > 0 else 0.0
        passed = normal_share >= 65 and normal_cpu >= idle_cpu * 2
        return ExperimentResult(
            name="Priority",
            observed=(
                f"Normal {normal_share:.1f}% ({normal_cpu:.1f}% CPU) | "
                f"Idle {idle_share:.1f}% ({idle_cpu:.1f}% CPU) "
                f"| elapsed {elapsed:.1f}s"
            ),
            threshold="Normal share >= 65% and Normal CPU >= 2x Idle",
            passed=passed,
        )
    finally:
        if idle is not None:
            cleanup(idle)
        if normal is not None:
            cleanup(normal)


def _print_results(results: list[ExperimentResult]) -> None:
    """Print the experiment measurements, thresholds, and pass status."""
    headers = ("Experiment", "Observed", "PASS threshold", "Result")
    rows = [
        (result.name, result.observed, result.threshold,
         "PASS" if result.passed else "FAIL")
        for result in results
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print(" | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(row[i].ljust(widths[i]) for i in range(len(row))))


def main() -> int:
    """Run all three manual resource-control proofs and return a status code."""
    manager = JobManager()
    if not manager.is_available():
        print(
            "FAIL: Windows Job Objects are unavailable; install pywin32 "
            "and run this script on Windows 10 or later."
        )
        return 1

    experiments = (
        ("CPU cap", lambda: _run_cpu_cap(manager)),
        ("Memory cap", lambda: _run_memory_cap(manager)),
        ("Priority", _run_priority),
    )
    results: list[ExperimentResult] = []
    for name, experiment in experiments:
        try:
            results.append(experiment())
        except Exception as error:
            results.append(
                ExperimentResult(
                    name=name,
                    observed=f"error: {error}",
                    threshold="experiment completes and meets its resource threshold",
                    passed=False,
                )
            )

    _print_results(results)
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
