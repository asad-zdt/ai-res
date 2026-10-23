"""Tests for the Tkinter dashboard's display helpers."""

import csv
from pathlib import Path

from gui.tk_app import (
    _draw_history_trends,
    _draw_prediction_ranges,
    _error_percent,
    _executable_from_icon,
    _history_statistics,
    _load_app_history,
    _load_profile_statistics,
    _metric_scales,
)


def test_error_percent_handles_zero_actual_value() -> None:
    assert _error_percent(5.0, 0.0) == "n/a"


def test_error_percent_reports_signed_relative_error() -> None:
    assert _error_percent(12.0, 10.0) == "20.0%"
    assert _error_percent(8.0, 10.0) == "-20.0%"


def test_metric_scales_are_positive() -> None:
    scales = _metric_scales()
    assert set(scales) == {"cpu_pct", "ram_mb", "disk_mbps", "net_kbps"}
    assert all(value > 0 for value in scales.values())


def test_executable_icon_parser_handles_quoted_path_and_icon_index(
    tmp_path,
) -> None:
    executable = tmp_path / "Installed App.exe"
    executable.write_bytes(b"binary")

    assert _executable_from_icon(f'"{executable}",0') == executable.resolve()


def test_load_app_history_filters_invalid_rows_and_limits_latest(
    tmp_path: Path,
) -> None:
    runs_path = tmp_path / "runs.csv"
    columns = ["app_name", "valid", "cpu_pct", "ram_mb", "disk_mbps", "net_kbps"]
    rows = [
        {"app_name": "app", "valid": "true", "cpu_pct": "1", "ram_mb": "10", "disk_mbps": "2", "net_kbps": "20"},
        {"app_name": "other", "valid": "true", "cpu_pct": "99", "ram_mb": "99", "disk_mbps": "99", "net_kbps": "99"},
        {"app_name": "app", "valid": "false", "cpu_pct": "50", "ram_mb": "50", "disk_mbps": "50", "net_kbps": "50"},
        {"app_name": "app", "valid": "true", "cpu_pct": "3", "ram_mb": "30", "disk_mbps": "4", "net_kbps": "40"},
    ]
    with runs_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    assert _load_app_history("app", runs_path, limit=1) == [
        {"cpu_pct": 3.0, "ram_mb": 30.0, "disk_mbps": 4.0, "net_kbps": 40.0}
    ]


def test_history_statistics_use_latest_five_runs() -> None:
    history = [
        {"cpu_pct": float(value), "ram_mb": float(value * 10), "disk_mbps": 1.0, "net_kbps": 2.0}
        for value in range(1, 7)
    ]

    statistics = _history_statistics(history)

    assert statistics is not None
    assert statistics["cpu_pct"] == {"min": 2.0, "average": 4.0, "max": 6.0}


def test_load_profile_statistics_reads_min_average_and_max(tmp_path: Path) -> None:
    profile_path = tmp_path / "profiles.csv"
    row = {"app_name": "app"}
    for metric, values in {
        "cpu_pct": (1, 2, 3),
        "ram_mb": (10, 20, 30),
        "disk_mbps": (0.1, 0.2, 0.3),
        "net_kbps": (4, 5, 6),
    }.items():
        row[f"hist_min_{metric}"] = str(values[0])
        row[f"hist_avg_{metric}"] = str(values[1])
        row[f"hist_max_{metric}"] = str(values[2])
    with profile_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)

    statistics = _load_profile_statistics("app", profile_path)

    assert statistics is not None
    assert statistics["ram_mb"] == {"min": 10.0, "average": 20.0, "max": 30.0}


class _RecordingCanvas:
    """Minimal Canvas test double that records drawing operations."""

    def __init__(self) -> None:
        self.operations: list[tuple[str, tuple, dict]] = []

    def winfo_width(self) -> int:
        return 600

    def winfo_height(self) -> int:
        return 300

    def delete(self, *args) -> None:
        self.operations.append(("delete", args, {}))

    def create_text(self, *args, **kwargs) -> None:
        self.operations.append(("text", args, kwargs))

    def create_line(self, *args, **kwargs) -> None:
        self.operations.append(("line", args, kwargs))

    def create_oval(self, *args, **kwargs) -> None:
        self.operations.append(("oval", args, kwargs))


def test_new_charts_draw_history_and_prediction_range() -> None:
    history_canvas = _RecordingCanvas()
    range_canvas = _RecordingCanvas()
    history = [
        {"cpu_pct": 10.0, "ram_mb": 20.0, "disk_mbps": 1.0, "net_kbps": 5.0},
        {"cpu_pct": 15.0, "ram_mb": 25.0, "disk_mbps": 2.0, "net_kbps": 8.0},
    ]
    statistics = _history_statistics(history)
    assert statistics is not None

    _draw_history_trends(history_canvas, history)
    _draw_prediction_ranges(
        range_canvas,
        statistics,
        {"cpu_pct": 12.0, "ram_mb": 22.0, "disk_mbps": 1.5, "net_kbps": 7.0},
    )

    assert sum(op[0] == "line" for op in history_canvas.operations) >= 4
    assert any(
        op[0] == "text" and op[2].get("text") == "CPU (%)"
        for op in history_canvas.operations
    )
    assert any(
        op[0] == "line" and op[2].get("fill") == "#e11d48"
        for op in range_canvas.operations
    )
