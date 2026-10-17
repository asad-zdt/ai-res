"""Predicted-versus-actual resource comparison visualizations."""

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_METRICS = (
    ("cpu_pct", "CPU", "%"),
    ("ram_mb", "RAM", "MB"),
    ("disk_mbps", "Disk", "MB/s"),
    ("net_kbps", "Network", "KB/s"),
)


def _metric_figure(
    title: str,
    unit: str,
    predicted: float,
    actual: float,
) -> go.Figure:
    """Create a compact grouped bar chart for one resource metric."""
    figure = go.Figure(
        data=[
            go.Bar(
                x=["Predicted", "Actual"],
                y=[predicted, actual],
                text=[f"{predicted:.2f} {unit}", f"{actual:.2f} {unit}"],
                textposition="outside",
                cliponaxis=False,
                marker_color=["#6366f1", "#14b8a6"],
            )
        ]
    )
    figure.update_layout(
        title={"text": title, "font": {"color": "#6b7280", "size": 16}},
        height=280,
        showlegend=False,
        margin={"l": 8, "r": 8, "t": 42, "b": 12},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#6b7280"},
        yaxis={"title": unit, "rangemode": "tozero"},
    )
    return figure


def _error_table(result: dict[str, Any]) -> pd.DataFrame:
    """Build the requested prediction, actual, and error summary table."""
    rows = []
    for metric, title, _ in _METRICS:
        predicted = float(result["predicted"][metric])
        actual = float(result["actual"][metric])
        error_pct = (
            "n/a"
            if actual == 0
            else f"{(predicted - actual) / actual * 100:.2f}%"
        )
        rows.append(
            {
                "Metric": title,
                "Predicted": predicted,
                "Actual": actual,
                "Absolute error": abs(predicted - actual),
                "Error %": error_pct,
            }
        )
    return pd.DataFrame(rows)


def _render_enforcement(result: dict[str, Any]) -> None:
    """Render admission, priority, enforcement, and duration as compact metrics."""
    enforcement = result["enforcement"]
    columns = st.columns(4)
    badges = (
        ("Admitted", "Yes" if enforcement["admitted"] else "No"),
        ("Niceness", str(enforcement.get("niceness", "n/a"))),
        ("Cgroup applied", "Yes" if enforcement["cgroup_applied"] else "No"),
        ("Duration", f"{float(result['duration_s']):.1f} s"),
    )
    for column, (label, value) in zip(columns, badges):
        with column:
            st.metric(label, value)
    reason = enforcement.get("reason")
    if reason:
        st.caption(f"Enforcement note: {reason}")


def render_compare_chart(result: dict[str, Any]) -> None:
    """Render resource comparison panels, error table, and enforcement metrics."""
    predicted = result["predicted"]
    actual = result["actual"]
    columns = st.columns(4)
    for column, (metric, title, unit) in zip(columns, _METRICS):
        with column:
            st.plotly_chart(
                _metric_figure(
                    title,
                    unit,
                    float(predicted[metric]),
                    float(actual[metric]),
                ),
                width="stretch",
            )

    st.dataframe(_error_table(result), hide_index=True, width="stretch")
    _render_enforcement(result)
