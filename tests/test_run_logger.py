"""Tests for CSV run logging and resume counting."""

import csv
from pathlib import Path

import collector.run_logger as run_logger
from collector.config_loader import AppSpec
from collector.run_logger import RUN_COLUMNS, _append_row, _read_app_counts, run_apps


def test_csv_rows_flush_and_valid_counts_resume(tmp_path: Path) -> None:
    """Append structured rows and count only valid rows when resuming."""
    runs_path = tmp_path / "runs.csv"
    row = {column: "" for column in RUN_COLUMNS}
    row.update({"run_id": "id-1", "app_name": "demo", "valid": True})

    _append_row(runs_path, row)
    row.update({"run_id": "id-2", "valid": False})
    _append_row(runs_path, row)

    valid_counts, total_counts = _read_app_counts(runs_path)
    assert valid_counts == {"demo": 1}
    assert total_counts == {"demo": 2}
    with runs_path.open("r", newline="", encoding="utf-8") as csv_file:
        records = list(csv.DictReader(csv_file))
    assert len(records) == 2
    assert records[0]["valid"] == "True"
    assert records[1]["valid"] == "False"


def test_run_columns_include_all_required_metrics() -> None:
    """The CSV writer schema includes run identity, metrics, and validity."""
    assert RUN_COLUMNS == [
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


def test_run_apps_appends_valid_attempt_and_prints_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Collect one valid run and summarize the selected application."""
    spec = AppSpec(
        name="demo",
        category="test",
        command=("python",),
        cwd=str(tmp_path),
        timeout_s=1.0,
        variants=(("--first",), ("--second",)),
        exe=Path("python"),
        exe_size_mb=1.0,
    )
    row = {"app_name": "demo", "valid": True}
    appended: list[tuple[Path, dict[str, object]]] = []
    summaries: list[tuple[Path, list[str]]] = []
    monkeypatch.setattr(run_logger, "_read_app_counts", lambda path: ({}, {}))
    monkeypatch.setattr(
        run_logger,
        "_run_once",
        lambda app, variant: {**row, "variant_index": variant},
    )
    monkeypatch.setattr(
        run_logger,
        "_append_row",
        lambda path, value: appended.append((path, value)),
    )
    monkeypatch.setattr(
        run_logger,
        "_print_summary",
        lambda path, names: summaries.append((path, names)),
    )
    runs_path = tmp_path / "runs.csv"

    run_apps({"demo": spec}, runs=1, runs_path=runs_path, cooldown=0)

    assert appended == [(runs_path, {"app_name": "demo", "valid": True, "variant_index": 0})]
    assert summaries == [(runs_path, ["demo"])]
