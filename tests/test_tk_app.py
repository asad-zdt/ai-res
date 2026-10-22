"""Tests for the Tkinter dashboard's display helpers."""

from gui.tk_app import _error_percent, _executable_from_icon, _metric_scales


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
