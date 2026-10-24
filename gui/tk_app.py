"""Windows Tkinter entry point and compatibility exports for dashboard tests."""

from __future__ import annotations

import tkinter as tk

from gui.application_catalog import executable_from_icon, installed_applications
from gui.dashboard_data import (
    METRICS,
    draw_comparison,
    draw_gauge,
    draw_history_trends,
    draw_prediction_ranges,
    error_percent,
    history_statistics,
    load_app_history,
    load_profile_statistics,
    metric_scales,
)
from gui.theme.manager import enable_windows_dpi_awareness, set_tk_scaling
from gui.theme import tokens
from gui.views.dashboard import DashboardView, _terminate_process_tree

ResourceApp = DashboardView
_METRICS = tuple((metric, title, unit) for metric, title, unit, _icon in METRICS)
_DEFAULT_SCALES = {"disk_mbps": 10.0, "net_kbps": 1000.0}

_executable_from_icon = executable_from_icon
_installed_applications = installed_applications
_metric_scales = metric_scales
_error_percent = error_percent
_load_app_history = load_app_history
_load_profile_statistics = load_profile_statistics
_history_statistics = history_statistics


def _draw_history_trends(
    canvas: tk.Canvas, history: list[dict[str, float]]
) -> None:
    """Draw the history chart with the shared light palette."""
    draw_history_trends(canvas, history, tokens.LIGHT)


def _draw_prediction_ranges(
    canvas: tk.Canvas,
    statistics: dict[str, dict[str, float]] | None,
    predictions: dict[str, float] | None = None,
) -> None:
    """Draw prediction ranges with the shared light palette."""
    draw_prediction_ranges(canvas, statistics, predictions, tokens.LIGHT)


def _draw_gauge(canvas: tk.Canvas, value: float, maximum: float) -> None:
    """Draw a resource gauge using the shared light palette."""
    draw_gauge(canvas, value, maximum, tokens.LIGHT)


def _draw_comparison(
    canvas: tk.Canvas,
    title: str,
    unit: str,
    predicted: float,
    actual: float,
) -> None:
    """Draw a predicted-versus-actual chart using the shared light palette."""
    draw_comparison(canvas, title, unit, predicted, actual, tokens.LIGHT)


def main() -> None:
    """Enable DPI awareness and run the Tkinter dashboard."""
    enable_windows_dpi_awareness()
    root = tk.Tk()
    set_tk_scaling(root)
    DashboardView(root)
    root.mainloop()


if __name__ == "__main__":
    main()
