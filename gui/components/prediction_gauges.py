"""Plotly gauges for predicted application resource requirements."""

from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import psutil
import streamlit as st

from config import resolve_path

_DEFAULT_SCALES = {"disk_mbps": 10.0, "net_kbps": 1000.0}
_FALLBACK_DATASETS = (
    ("data", "processed", "dataset.csv"),
    ("data", "sample", "sample_dataset.csv"),
)
_METRICS = (
    ("cpu_pct", "CPU", "%"),
    ("ram_mb", "RAM", "MB"),
    ("disk_mbps", "Disk", "MB/s"),
    ("net_kbps", "Network", "KB/s"),
)


@st.cache_data
def _disk_network_scales() -> dict[str, float]:
    """Return cached gauge maxima for disk and network from available datasets."""
    for path_parts in _FALLBACK_DATASETS:
        path = resolve_path(*path_parts)
        try:
            frame = pd.read_csv(path, usecols=["disk_mbps", "net_kbps"])
        except (OSError, ValueError, pd.errors.ParserError):
            continue

        scales: dict[str, float] = {}
        for column, fallback in _DEFAULT_SCALES.items():
            maximum = pd.to_numeric(frame[column], errors="coerce").max()
            if pd.notna(maximum) and maximum > 0:
                scales[column] = float(maximum) * 1.5
            else:
                scales[column] = fallback
        return scales
    return dict(_DEFAULT_SCALES)


def _system_scales() -> dict[str, float]:
    """Return current CPU and physical memory gauge maxima."""
    logical_cores = psutil.cpu_count(logical=True) or 1
    total_ram_mb = psutil.virtual_memory().total / (1024 * 1024)
    return {
        "cpu_pct": float(logical_cores * 100),
        "ram_mb": float(total_ram_mb),
    }


def _gauge_figure(
    title: str,
    value: float,
    unit: str,
    maximum: float,
) -> go.Figure:
    """Build a theme-neutral gauge with green, amber, and red scale bands."""
    safe_maximum = max(float(maximum), 1e-9)
    figure = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number={"suffix": f" {unit}", "font": {"color": "#6b7280", "size": 20}},
            title={"text": title, "font": {"color": "#6b7280", "size": 16}},
            gauge={
                "axis": {
                    "range": [0, safe_maximum],
                    "tickfont": {"color": "#6b7280"},
                },
                "bar": {"color": "#64748b"},
                "steps": [
                    {"range": [0, safe_maximum * 0.5], "color": "#bbf7d0"},
                    {
                        "range": [safe_maximum * 0.5, safe_maximum * 0.8],
                        "color": "#fde68a",
                    },
                    {
                        "range": [safe_maximum * 0.8, safe_maximum],
                        "color": "#fecaca",
                    },
                ],
                "threshold": {
                    "line": {"color": "#475569", "width": 3},
                    "thickness": 0.8,
                    "value": min(max(value, 0.0), safe_maximum),
                },
            },
        )
    )
    figure.update_layout(
        height=220,
        margin={"l": 12, "r": 12, "t": 32, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#6b7280"},
    )
    return figure


def render_prediction_gauges(prediction: dict[str, Any]) -> None:
    """Render four resource prediction gauges and their scale percentages."""
    scales = {**_system_scales(), **_disk_network_scales()}
    columns = st.columns(4)
    for column, (metric, title, unit) in zip(columns, _METRICS):
        try:
            value = float(prediction[metric])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"prediction must include a numeric {metric!r}") from error
        if value < 0:
            raise ValueError(f"prediction value for {metric!r} cannot be negative")

        maximum = scales[metric]
        with column:
            st.plotly_chart(
                _gauge_figure(title, value, unit, maximum),
                width="stretch",
            )
            st.caption(f"{value / maximum * 100:.1f}% of scale")
