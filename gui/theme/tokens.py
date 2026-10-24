"""Material-inspired design tokens for the desktop interface."""

from __future__ import annotations

LIGHT = {
    "primary": "#1A73E8",
    "primary_hover": "#1765CC",
    "primary_pressed": "#1558B0",
    "surface": "#FFFFFF",
    "surface_alt": "#F1F3F4",
    "background": "#F8F9FA",
    "outline": "#DADCE0",
    "outline_focus": "#1A73E8",
    "text": "#202124",
    "text_secondary": "#5F6368",
    "success": "#188038",
    "warning": "#F9AB00",
    "error": "#D93025",
    "gauge_track": "#E8EAED",
    "grid": "#E8EAED",
    "range": "#AECBFA",
    "prediction": "#D93025",
    "actual": "#188038",
    "white": "#FFFFFF",
    "selection": "#E8F0FE",
    "stripe": "#F8F9FA",
}

DARK = {
    "primary": "#8AB4F8",
    "primary_hover": "#A8C7FA",
    "primary_pressed": "#669DF6",
    "surface": "#202124",
    "surface_alt": "#292A2D",
    "background": "#17181A",
    "outline": "#5F6368",
    "outline_focus": "#8AB4F8",
    "text": "#E8EAED",
    "text_secondary": "#BDC1C6",
    "success": "#81C995",
    "warning": "#FDD663",
    "error": "#F28B82",
    "gauge_track": "#3C4043",
    "grid": "#3C4043",
    "range": "#3C5A86",
    "prediction": "#F28B82",
    "actual": "#81C995",
    "white": "#FFFFFF",
    "selection": "#26354A",
    "stripe": "#292A2D",
}

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 24,
    "xl": 32,
    "card": 18,
}

RADIUS = {"card": 10, "chip": 16, "button": 8}

SIZES = {
    "window_width": 1200,
    "window_height": 820,
    "min_width": 1100,
    "min_height": 720,
    "radius": 10,
    "border": 1,
    "gauge_height": 18,
    "chart_height": 290,
    "small_chart_height": 250,
    "status_height": 38,
    "icon": 22,
    "navigation_width": 188,
    "picker_width": 34,
    "metric_gauge_min_width": 220,
    "comparison_min_width": 300,
    "progress_width": 180,
    "progress_max": 100,
    "icon_stroke": 2,
    "small_icon_stroke": 1,
    "curve_steps": 12,
    "snackbar_duration_ms": 3200,
}

CHART = {
    "min_width": 560,
    "min_height": 280,
    "empty_width": 500,
    "empty_height": 260,
    "history_left": 58,
    "history_right": 16,
    "history_top": 38,
    "history_bottom": 34,
    "range_left": 64,
    "range_right": 20,
    "point_radius": 3,
    "line_width": 2,
    "comparison_left": 24,
    "comparison_right": 16,
    "comparison_top": 32,
    "comparison_bottom": 32,
    "comparison_bar_width": 64,
    "tooltip_offset": 10,
    "history_title_top": 12,
    "empty_comparison_width": 300,
    "empty_comparison_height": 220,
    "history_scale_margin": 1.15,
    "range_center_fraction": 0.55,
    "comparison_max_margin": 1.2,
    "comparison_predicted_center": 0.34,
    "comparison_actual_center": 0.72,
    "gauge_top": 4,
}

GAUGE_THRESHOLDS = {"success_max": 0.5, "warning_max": 0.8}

DPI = {"base": 96.0, "point": 72.0}

TASK_SETTINGS = {
    "prepare_runs": 8,
    "prepare_observation_seconds": 15,
    "api_log_detail_limit": 1200,
    "minimum_history_runs": 20,
    "error_high_percent": 50.0,
    "error_medium_percent": 20.0,
}

TABLE = {
    "metric_width": 140,
    "value_width": 130,
    "absolute_width": 160,
    "error_width": 120,
    "history_time_width": 115,
    "history_app_width": 210,
    "history_error_width": 115,
    "error_rows": 4,
    "recent_rows": 6,
    "recent_limit": 20,
}

TEXT_LAYOUT = {
    "dialog_wrap": 460,
    "error_wrap": 540,
    "detail_lines": 8,
    "detail_columns": 66,
    "page_wrap": 850,
}

INTERACTION = {"api_attempts": 40, "api_retry_ms": 500, "worker_poll_ms": 16}

ELEVATION = {"card": "outlined", "snackbar": "raised"}

TYPOGRAPHY = {
    "headline": 22,
    "title": 16,
    "body": 13,
    "caption": 11,
    "button": 12,
    "weight_regular": "normal",
    "weight_medium": "bold",
}

FONT_CANDIDATES = ("Google Sans", "Roboto", "Segoe UI")

METRICS = (
    ("cpu_pct", "CPU", "%", "cpu"),
    ("ram_mb", "Memory", "MB", "ram"),
    ("disk_mbps", "Disk I/O", "MB/s", "disk"),
    ("net_kbps", "Network", "KB/s", "network"),
)

PAGE_NAMES = (
    ("overview", "Overview"),
    ("history", "Run History"),
    ("range", "Prediction Range"),
    ("comparison", "Comparison"),
    ("settings", "Settings / About"),
)

TASK_PHASES = {
    "health": "Checking API",
    "predict": "Predicting resource demand",
    "compare": "Submitting compare request (API performs admission, launch, measurement, comparison)",
    "collect": "Collecting selected app history",
    "dataset": "Building training data",
    "train": "Training model",
    "evaluate": "Evaluating model",
}
