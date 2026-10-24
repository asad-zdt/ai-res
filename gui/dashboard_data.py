"""Data loading, formatting, and chart drawing helpers for the dashboard."""

from __future__ import annotations

import csv
from pathlib import Path
import tkinter as tk
from typing import Any

import psutil

from config import resolve_path
from gui.theme import tokens

METRICS = tokens.METRICS
DEFAULT_SCALES = {"disk_mbps": 10.0, "net_kbps": 1000.0}


def metric_scales() -> dict[str, float]:
    """Return system-capacity scales plus actual collected sample maxima."""
    scales = {
        "cpu_pct": float((psutil.cpu_count(logical=True) or 1) * 100),
        "ram_mb": psutil.virtual_memory().total / (1024 * 1024),
        **DEFAULT_SCALES,
    }
    for relative_path in (
        Path("data") / "processed" / "dataset.csv",
        Path("data") / "sample" / "sample_dataset.csv",
    ):
        path = resolve_path(*relative_path.parts)
        try:
            with path.open("r", newline="", encoding="utf-8") as file:
                maxima = {metric: 0.0 for metric in DEFAULT_SCALES}
                for row in csv.DictReader(file):
                    for metric in maxima:
                        try:
                            maxima[metric] = max(maxima[metric], float(row[metric]))
                        except (KeyError, TypeError, ValueError):
                            continue
        except OSError:
            continue
        for metric, fallback in DEFAULT_SCALES.items():
            scales[metric] = maxima[metric] * 1.5 if maxima[metric] > 0 else fallback
        break
    return scales


def error_percent(predicted: float, actual: float) -> str:
    """Format signed prediction error relative to the measured value."""
    return "n/a" if actual == 0 else f"{(predicted - actual) / actual * 100:.1f}%"


def load_app_history(
    app_name: str,
    runs_path: Path | None = None,
    limit: int = tokens.TASK_SETTINGS["minimum_history_runs"],
) -> list[dict[str, float]]:
    """Read the latest valid resource measurements for one application."""
    if limit < 1:
        raise ValueError("limit must be positive")
    path = runs_path or resolve_path("data", "raw", "runs.csv")
    try:
        with path.open("r", newline="", encoding="utf-8") as csv_file:
            history = []
            for row in csv.DictReader(csv_file):
                if row.get("app_name") != app_name:
                    continue
                if (row.get("valid") or "").strip().casefold() != "true":
                    continue
                try:
                    values = {
                        metric: float(row[metric]) for metric, _, _, _ in METRICS
                    }
                except (KeyError, TypeError, ValueError):
                    continue
                history.append(values)
    except FileNotFoundError:
        return []
    return history[-limit:]


def load_profile_statistics(
    app_name: str, profile_path: Path | None = None
) -> dict[str, dict[str, float]] | None:
    """Load historical minimum, average, and maximum values from profiles."""
    path = profile_path or resolve_path("data", "processed", "app_profiles.csv")
    try:
        with path.open("r", newline="", encoding="utf-8") as csv_file:
            for row in csv.DictReader(csv_file):
                if row.get("app_name") != app_name:
                    continue
                return {
                    metric: {
                        key: float(row[f"hist_{column}_{metric}"])
                        for key, column in (
                            ("min", "min"),
                            ("average", "avg"),
                            ("max", "max"),
                        )
                    }
                    for metric, _, _, _ in METRICS
                }
    except FileNotFoundError:
        return None
    return None


def history_statistics(
    history: list[dict[str, float]], window: int = 5
) -> dict[str, dict[str, float]] | None:
    """Calculate min, average, and max from the latest valid run window."""
    if not history:
        return None
    recent = history[-window:]
    return {
        metric: {
            "min": min(row[metric] for row in recent),
            "average": sum(row[metric] for row in recent) / len(recent),
            "max": max(row[metric] for row in recent),
        }
        for metric, _, _, _ in METRICS
    }


def draw_history_trends(
    canvas: tk.Canvas,
    history: list[dict[str, float]],
    colors: dict[str, str] | None = None,
    font_family: str = "Segoe UI",
) -> None:
    """Draw four compact, real-data trend charts with run/value hover tips."""
    palette = colors or tokens.LIGHT
    canvas.delete("all")
    if not history:
        canvas.create_text(
            max(canvas.winfo_width(), tokens.CHART["empty_width"]) / 2,
            max(canvas.winfo_height(), tokens.CHART["empty_height"]) / 2,
            text="No valid run history for this app yet.",
            fill=palette["text_secondary"],
        )
        return

    width = max(canvas.winfo_width(), tokens.CHART["min_width"])
    height = max(canvas.winfo_height(), tokens.CHART["min_height"])
    cell_width, cell_height = width / 2, height / 2
    for index, (metric, title, unit, _icon) in enumerate(METRICS):
        column, row = index % 2, index // 2
        x0, y0 = column * cell_width, row * cell_height
        left = x0 + tokens.CHART["history_left"]
        right = x0 + cell_width - tokens.CHART["history_right"]
        top = y0 + tokens.CHART["history_top"]
        bottom = y0 + cell_height - tokens.CHART["history_bottom"]
        values = [run[metric] for run in history]
        scale_max = (
            max(values, default=0.0) * tokens.CHART["history_scale_margin"] or 1.0
        )
        canvas.create_text(
            x0 + tokens.SPACING["sm"], y0 + tokens.CHART["history_title_top"],
            text=f"{title} ({unit})", anchor="w",
            font=(font_family, tokens.TYPOGRAPHY["body"], "bold"),
            fill=palette["text"],
        )
        _grid_axes(canvas, left, top, right, bottom, palette)
        canvas.create_text(
            left - tokens.SPACING["xs"], top, text=f"{scale_max:.1f}",
            anchor="e", fill=palette["text_secondary"],
        )
        canvas.create_text(
            left - tokens.SPACING["xs"], bottom, text="0",
            anchor="e", fill=palette["text_secondary"],
        )
        points: list[float] = []
        for point_index, value in enumerate(values):
            fraction_x = point_index / max(len(values) - 1, 1)
            x = left + (right - left) * fraction_x
            y = bottom - (bottom - top) * value / scale_max
            points.extend((x, y))
            canvas.create_oval(
                x - tokens.CHART["point_radius"], y - tokens.CHART["point_radius"],
                x + tokens.CHART["point_radius"], y + tokens.CHART["point_radius"],
                fill=palette["primary"], outline="",
                tags=(f"point-{metric}-{point_index}",),
            )
            if hasattr(canvas, "tag_bind"):
                canvas.tag_bind(
                    f"point-{metric}-{point_index}",
                    "<Enter>",
                    lambda event, run_no=point_index + 1, val=value, measure=unit:
                        _show_canvas_tip(
                            event, canvas, f"Run {run_no}: {val:.2f} {measure}",
                            palette,
                        ),
                )
                canvas.tag_bind(
                    f"point-{metric}-{point_index}", "<Leave>",
                    lambda _event: _hide_canvas_tip(canvas),
                )
        if len(points) >= 4:
            canvas.create_line(
                *points, fill=palette["primary"], width=2, smooth=True
            )
        canvas.create_text(
            left, bottom + tokens.SPACING["md"], text="Run 1",
            anchor="w", fill=palette["text_secondary"],
        )
        canvas.create_text(
            right, bottom + tokens.SPACING["md"],
            text=f"Run {len(values)}", anchor="e",
            fill=palette["text_secondary"],
        )


def draw_prediction_ranges(
    canvas: tk.Canvas,
    statistics: dict[str, dict[str, float]] | None,
    predictions: dict[str, float] | None = None,
    colors: dict[str, str] | None = None,
    font_family: str = "Segoe UI",
) -> None:
    """Draw actual historical range bands, average ticks, and prediction markers."""
    palette = colors or tokens.LIGHT
    canvas.delete("all")
    if not statistics:
        canvas.create_text(
            max(canvas.winfo_width(), tokens.CHART["empty_width"]) / 2,
            max(canvas.winfo_height(), tokens.CHART["empty_height"]) / 2,
            text="Collect valid runs to see this app's historical range.",
            fill=palette["text_secondary"],
        )
        return
    width = max(canvas.winfo_width(), tokens.CHART["min_width"])
    height = max(canvas.winfo_height(), tokens.CHART["min_height"])
    cell_width, cell_height = width / 2, height / 2
    for index, (metric, title, unit, _icon) in enumerate(METRICS):
        values = statistics[metric]
        column, row = index % 2, index // 2
        x0, y0 = column * cell_width, row * cell_height
        left = x0 + tokens.CHART["range_left"]
        right = x0 + cell_width - tokens.CHART["range_right"]
        center_y = y0 + cell_height * tokens.CHART["range_center_fraction"]
        minimum, average, maximum = (
            values["min"], values["average"], values["max"]
        )
        max_scale = max(maximum, float((predictions or {}).get(metric, 0.0)), 1e-9)

        def to_x(value: float) -> float:
            return left + (right - left) * min(max(value / max_scale, 0.0), 1.0)

        canvas.create_text(
            x0 + tokens.SPACING["sm"], y0 + tokens.SPACING["md"],
            text=f"{title} ({unit})", anchor="w",
            font=(font_family, tokens.TYPOGRAPHY["body"], "bold"),
            fill=palette["text"],
        )
        canvas.create_line(
            left, center_y, right, center_y,
            fill=palette["gauge_track"], width=tokens.SPACING["sm"],
        )
        canvas.create_line(
            to_x(minimum), center_y, to_x(maximum), center_y,
            fill=palette["range"], width=tokens.SPACING["sm"],
        )
        canvas.create_line(
            to_x(average), center_y - tokens.SPACING["sm"],
            to_x(average), center_y + tokens.SPACING["sm"],
            fill=palette["primary"], width=2,
        )
        if predictions is not None and metric in predictions:
            predicted_x = to_x(float(predictions[metric]))
            canvas.create_line(
                predicted_x, center_y - tokens.SPACING["lg"],
                predicted_x, center_y + tokens.SPACING["lg"],
                fill=palette["prediction"], width=2,
            )
            canvas.create_text(
                predicted_x, center_y - tokens.SPACING["lg"] - tokens.SPACING["xs"],
                text=f"Prediction {predictions[metric]:.2f}",
                anchor="s", fill=palette["prediction"],
            )
        canvas.create_text(
            left, center_y + tokens.SPACING["lg"], text=f"Min {minimum:.2f}",
            anchor="w", fill=palette["text_secondary"],
        )
        canvas.create_text(
            (left + right) / 2, center_y + tokens.SPACING["lg"],
            text=f"Avg {average:.2f}", anchor="center",
            fill=palette["text_secondary"],
        )
        canvas.create_text(
            right, center_y + tokens.SPACING["lg"], text=f"Max {maximum:.2f}",
            anchor="e", fill=palette["text_secondary"],
        )
    canvas.create_text(
        width - tokens.SPACING["md"], height - tokens.SPACING["sm"],
        text="Range: actual collected data   Average: blue tick   Prediction: red",
        anchor="se", fill=palette["text_secondary"],
    )


def gauge_color(value: float, maximum: float, colors: dict[str, str]) -> str:
    """Return the semantic green/amber/red color at the relative gauge level."""
    fraction = min(max(value / max(maximum, 1e-9), 0.0), 1.0)
    if fraction < tokens.GAUGE_THRESHOLDS["success_max"]:
        return colors["success"]
    if fraction < tokens.GAUGE_THRESHOLDS["warning_max"]:
        return colors["warning"]
    return colors["error"]


def draw_gauge(
    canvas: tk.Canvas,
    value: float,
    maximum: float,
    colors: dict[str, str] | None = None,
) -> None:
    """Draw a horizontal gauge with green/amber/red semantic thresholds."""
    palette = colors or tokens.LIGHT
    canvas.delete("all")
    width = max(canvas.winfo_width(), tokens.SIZES["metric_gauge_min_width"])
    height = tokens.SIZES["gauge_height"] + tokens.SPACING["sm"]
    top = tokens.SPACING["xs"]
    bottom = top + tokens.SIZES["gauge_height"]
    fraction = min(max(value / max(maximum, 1e-9), 0.0), 1.0)
    canvas.create_rectangle(
        0, top, width, bottom, fill=palette["gauge_track"], outline=""
    )
    if fraction > 0:
        canvas.create_rectangle(
            0, top, max(width * fraction, 1), bottom,
            fill=gauge_color(value, maximum, palette), outline="",
        )
    canvas.configure(height=height)


def draw_comparison(
    canvas: tk.Canvas,
    title: str,
    unit: str,
    predicted: float,
    actual: float,
    colors: dict[str, str] | None = None,
    font_family: str = "Segoe UI",
) -> None:
    """Draw paired bars for the real predicted and observed values."""
    palette = colors or tokens.LIGHT
    canvas.delete("all")
    width = max(canvas.winfo_width(), tokens.SIZES["comparison_min_width"])
    height = max(canvas.winfo_height(), tokens.SIZES["small_chart_height"])
    left = tokens.CHART["comparison_left"]
    right = width - tokens.CHART["comparison_right"]
    top = tokens.CHART["comparison_top"]
    bottom = height - tokens.CHART["comparison_bottom"]
    canvas.create_text(
        left, tokens.SPACING["md"], anchor="w", text=title,
        font=(font_family, tokens.TYPOGRAPHY["body"], "bold"),
        fill=palette["text"],
    )
    canvas.create_line(left, top, left, bottom, fill=palette["outline"])
    canvas.create_line(left, bottom, right, bottom, fill=palette["outline"])
    maximum = max(predicted, actual, 1e-9) * tokens.CHART["comparison_max_margin"]
    bar_width = min(
        tokens.CHART["comparison_bar_width"], (right - left) / 4
    )
    centers = (
        left + (right - left) * tokens.CHART["comparison_predicted_center"],
        left + (right - left) * tokens.CHART["comparison_actual_center"],
    )
    for center, value, label, color in (
        (centers[0], predicted, "Predicted", palette["primary"]),
        (centers[1], actual, "Actual", palette["actual"]),
    ):
        bar_height = (bottom - top) * value / maximum
        x0, x1 = center - bar_width / 2, center + bar_width / 2
        y0 = bottom - bar_height
        canvas.create_rectangle(x0, y0, x1, bottom, fill=color, outline="")
        canvas.create_text(
            center, max(top - tokens.SPACING["xs"], y0 - tokens.SPACING["sm"]),
            text=f"{value:.2f} {unit}", fill=palette["text"],
        )
        canvas.create_text(
            center, bottom + tokens.SPACING["md"], text=label,
            fill=palette["text_secondary"],
        )


def _grid_axes(
    canvas: tk.Canvas,
    left: float,
    top: float,
    right: float,
    bottom: float,
    colors: dict[str, str],
) -> None:
    """Draw light gridlines and axes for a compact chart."""
    for division in range(1, 4):
        y = top + (bottom - top) * division / 4
        canvas.create_line(left, y, right, y, fill=colors["grid"])
    canvas.create_line(left, top, left, bottom, fill=colors["outline"])
    canvas.create_line(left, bottom, right, bottom, fill=colors["outline"])


def _show_canvas_tip(
    event: tk.Event[tk.Misc],
    canvas: tk.Canvas,
    text: str,
    colors: dict[str, str],
) -> None:
    """Show a small tooltip for a chart point."""
    _hide_canvas_tip(canvas)
    tip = tk.Toplevel(canvas)
    tip.wm_overrideredirect(True)
    tip.wm_geometry(
        f"+{event.x_root + tokens.CHART['tooltip_offset']}"
        f"+{event.y_root + tokens.CHART['tooltip_offset']}"
    )
    label = tk.Label(
        tip, text=text, background=colors["text"],
        foreground=colors["surface"], padx=tokens.SPACING["sm"],
        pady=tokens.SPACING["xs"],
    )
    label.pack()
    setattr(canvas, "_chart_tip", tip)


def _hide_canvas_tip(canvas: tk.Canvas) -> None:
    """Remove a chart tooltip if one is visible."""
    tip: Any = getattr(canvas, "_chart_tip", None)
    if tip is not None:
        try:
            tip.destroy()
        except tk.TclError:
            pass
        setattr(canvas, "_chart_tip", None)
