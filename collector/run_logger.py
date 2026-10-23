"""Run configured workloads and append measured resource usage to CSV."""

import argparse
import csv
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collector.config_loader import AppSpec
from collector.launcher import LaunchedApp, cleanup, launch
from collector.monitor import MonitorSamples, monitor_process, summarize
from collector.user_apps import load_all_apps
from config import resolve_path

RUN_COLUMNS = [
    "run_id",
    "timestamp",
    "app_name",
    "app_category",
    "exe_size_mb",
    "variant_index",
    "cpu_pct",
    "ram_mb",
    "disk_mbps",
    "net_kbps",
    "duration_s",
    "exit_code",
    "n_samples",
    "valid",
]
_METRIC_COLUMNS = ("cpu_pct", "ram_mb", "disk_mbps", "net_kbps")
_DEFAULT_RUNS_PATH = resolve_path("data", "raw", "runs.csv")


def _read_app_counts(runs_path: Path) -> tuple[dict[str, int], dict[str, int]]:
    """Count existing valid and total rows per app for resume and variant cycling."""
    valid_counts: dict[str, int] = {}
    total_counts: dict[str, int] = {}
    if not runs_path.is_file():
        return valid_counts, total_counts
    with runs_path.open("r", newline="", encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            app_name = row.get("app_name")
            if not app_name:
                continue
            total_counts[app_name] = total_counts.get(app_name, 0) + 1
            if (row.get("valid") or "").strip().lower() == "true":
                valid_counts[app_name] = valid_counts.get(app_name, 0) + 1
    return valid_counts, total_counts


def _append_row(runs_path: Path, row: dict[str, object]) -> None:
    """Append one run record, creating the CSV header if needed."""
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not runs_path.exists() or runs_path.stat().st_size == 0
    with runs_path.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=RUN_COLUMNS)
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
        csv_file.flush()


def _valid_run(
    spec: AppSpec,
    exit_code: int | None,
    samples: MonitorSamples,
    metrics: dict[str, float],
) -> bool:
    """Apply workload-specific validity rules to a measured run."""
    if spec.category == "desktop_application":
        if samples.timed_out:
            return len(samples) >= 2 and metrics["ram_mb"] > 0
        return exit_code == 0 and len(samples) >= 1 and metrics["ram_mb"] > 0
    return (
        exit_code == 0
        and len(samples) >= 3
        and not samples.timed_out
        and metrics["cpu_pct"] > 0
        and metrics["ram_mb"] > 0
    )


def _run_once(
    spec: AppSpec,
    variant_index: int,
) -> dict[str, object]:
    """Launch, monitor, summarize, and clean up one workload attempt."""
    launched: LaunchedApp | None = None
    start_time = time.monotonic()
    try:
        launched = launch(spec, variant_index=variant_index)
        samples = monitor_process(launched.popen, timeout_s=spec.timeout_s)
        duration_s = time.monotonic() - start_time
        exit_code = launched.popen.wait(timeout=3)
        metrics = summarize(samples) if samples else {
            metric: 0.0 for metric in _METRIC_COLUMNS
        }
        valid = _valid_run(spec, exit_code, samples, metrics)
    except KeyboardInterrupt:
        raise
    except Exception as error:
        duration_s = time.monotonic() - start_time
        exit_code = launched.popen.poll() if launched is not None else None
        samples = MonitorSamples()
        metrics = {metric: 0.0 for metric in _METRIC_COLUMNS}
        valid = False
        print(f"Run attempt failed for {spec.name}: {error}")
    finally:
        if launched is not None:
            cleanup(launched)

    return {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app_name": spec.name,
        "app_category": spec.category,
        "exe_size_mb": spec.exe_size_mb,
        "variant_index": variant_index,
        **metrics,
        "duration_s": duration_s,
        "exit_code": exit_code,
        "n_samples": len(samples),
        "valid": valid,
    }


def _print_summary(runs_path: Path, app_names: list[str]) -> None:
    """Print valid-row counts and mean metrics for the selected applications."""
    totals = {name: 0 for name in app_names}
    metric_sums = {
        name: {metric: 0.0 for metric in _METRIC_COLUMNS}
        for name in app_names
    }
    if runs_path.is_file():
        with runs_path.open("r", newline="", encoding="utf-8") as csv_file:
            for row in csv.DictReader(csv_file):
                name = row.get("app_name")
                if name not in totals or (row.get("valid") or "").lower() != "true":
                    continue
                try:
                    for metric in _METRIC_COLUMNS:
                        metric_sums[name][metric] += float(row[metric])
                except (KeyError, TypeError, ValueError):
                    continue
                totals[name] += 1

    headers = ("app", "valid runs", *_METRIC_COLUMNS)
    rows = []
    for name in app_names:
        count = totals[name]
        means = [
            f"{metric_sums[name][metric] / count:.2f}" if count else "-"
            for metric in _METRIC_COLUMNS
        ]
        rows.append((name, str(count), *means))
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def run_apps(
    apps: dict[str, AppSpec],
    runs: int,
    runs_path: Path,
    only: list[str] | None = None,
    cooldown: float = 5.0,
) -> None:
    """Run selected apps until each has the requested number of valid rows."""
    if runs < 1:
        raise ValueError("runs must be at least 1")
    if cooldown < 0:
        raise ValueError("cooldown cannot be negative")

    app_names = list(apps) if only is None else only
    unknown_names = [name for name in app_names if name not in apps]
    if unknown_names:
        raise ValueError(f"Unknown app names: {unknown_names}")
    valid_counts, total_counts = _read_app_counts(runs_path)

    try:
        for name in app_names:
            spec = apps[name]
            while valid_counts.get(name, 0) < runs:
                attempts_for_goal = 0
                while attempts_for_goal < 3:
                    variant_index = total_counts.get(name, 0) % len(spec.variants)
                    row = _run_once(spec, variant_index)
                    _append_row(runs_path, row)
                    total_counts[name] = total_counts.get(name, 0) + 1
                    attempts_for_goal += 1
                    if row["valid"]:
                        valid_counts[name] = valid_counts.get(name, 0) + 1
                        break
                    if cooldown > 0 and attempts_for_goal < 3:
                        time.sleep(cooldown)
                if attempts_for_goal == 3 and not row["valid"]:
                    print(
                        f"Giving up on {name} after 3 invalid attempts for "
                        f"one requested valid run."
                    )
                    break
                if cooldown > 0 and valid_counts.get(name, 0) < runs:
                    time.sleep(cooldown)
    except KeyboardInterrupt:
        print("\nInterrupted; active workload cleaned up.")
    finally:
        _print_summary(runs_path, app_names)


def main() -> None:
    """Parse CLI options and collect the requested valid workload runs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=8)
    parser.add_argument("--only")
    parser.add_argument("--cooldown", type=float, default=5.0)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.cooldown < 0:
        parser.error("--cooldown cannot be negative")

    try:
        apps = load_all_apps()
        selected = (
            [name.strip() for name in args.only.split(",") if name.strip()]
            if args.only
            else None
        )
        run_apps(
            apps,
            runs=args.runs,
            runs_path=_DEFAULT_RUNS_PATH,
            only=selected,
            cooldown=args.cooldown,
        )
    except (FileNotFoundError, ValueError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
