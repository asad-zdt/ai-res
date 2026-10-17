"""Tests for predicted-versus-actual comparison rendering."""

from typing import Any

import pytest

from gui.components import compare_chart
from gui.components.app_picker import render_app_picker
from gui.api_client import ApiError


class FakeColumn:
    """Capture Streamlit chart, table, and metric calls in a column."""

    def __init__(self, streamlit: "FakeStreamlit") -> None:
        self.streamlit = streamlit

    def __enter__(self) -> "FakeColumn":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __getattr__(self, name: str):
        return getattr(self.streamlit, name)


class FakeStreamlit:
    """Minimal Streamlit API stub for comparison view tests."""

    def __init__(self) -> None:
        self.charts = []
        self.tables = []
        self.metrics = []
        self.captions = []

    def columns(self, count: int) -> list[FakeColumn]:
        return [FakeColumn(self) for _ in range(count)]

    def plotly_chart(self, figure, **kwargs: Any) -> None:
        self.charts.append(figure)

    def dataframe(self, frame, **kwargs: Any) -> None:
        self.tables.append(frame)

    def metric(self, label: str, value: str) -> None:
        self.metrics.append((label, value))

    def caption(self, text: str) -> None:
        self.captions.append(text)


def _result() -> dict[str, Any]:
    return {
        "app_name": "cpu_burn",
        "predicted": {
            "cpu_pct": 100.0,
            "ram_mb": 100.0,
            "disk_mbps": 2.0,
            "net_kbps": 0.0,
        },
        "actual": {
            "cpu_pct": 80.0,
            "ram_mb": 0.0,
            "disk_mbps": 1.0,
            "net_kbps": 0.0,
        },
        "duration_s": 12.5,
        "enforcement": {
            "admitted": True,
            "reason": "No Job Object available",
            "niceness": 5,
            "cgroup_applied": False,
        },
    }


def test_compare_chart_renders_four_charts_table_and_badges(monkeypatch) -> None:
    """Render per-metric bars, error table, and enforcement details."""
    fake_st = FakeStreamlit()
    monkeypatch.setattr(compare_chart, "st", fake_st)

    compare_chart.render_compare_chart(_result())

    assert len(fake_st.charts) == 4
    assert [list(chart.data[0].x) for chart in fake_st.charts] == [
        ["Predicted", "Actual"]
    ] * 4
    table = fake_st.tables[0]
    assert list(table.columns) == [
        "Metric",
        "Predicted",
        "Actual",
        "Absolute error",
        "Error %",
    ]
    assert table.iloc[1]["Error %"] == "n/a"
    assert table.iloc[0]["Error %"] == "25.00%"
    assert fake_st.metrics == [
        ("Admitted", "Yes"),
        ("Niceness", "5"),
        ("Cgroup applied", "No"),
        ("Duration", "12.5 s"),
    ]
    assert fake_st.captions == ["Enforcement note: No Job Object available"]


def test_compare_picker_stores_success_and_history(monkeypatch) -> None:
    """Persist a successful comparison and its error percentages."""
    from tests.test_app_picker import FakeStreamlit

    fake_st = FakeStreamlit()
    fake_st.clicked = False
    fake_st.compare_clicked = True
    monkeypatch.setattr("gui.components.app_picker.st", fake_st)
    monkeypatch.setattr(
        "gui.components.app_picker.load_apps",
        lambda: {
            "cpu_burn": type(
                "App",
                (),
                {"category": "synthetic_cpu", "exe_size_mb": 1.0},
            )()
        },
    )

    class FakeApi:
        def run_and_compare(self, app_name: str) -> dict[str, Any]:
            return _result()

    selected, predicted, compared = render_app_picker(FakeApi())  # type: ignore[arg-type]

    assert (selected, predicted, compared) == ("cpu_burn", False, True)
    assert fake_st.session_state["comparison"]["app_name"] == "cpu_burn"
    history = fake_st.session_state["comparison_history"]
    assert len(history) == 1
    assert history[0]["cpu_pct error %"] == "25.0%"
    assert history[0]["ram_mb error %"] == "n/a"


def test_admission_refusal_is_warning_and_clears_old_comparison(
    monkeypatch,
) -> None:
    """Handle HTTP 409 inline and do not leave an old chart displayed."""
    from tests.test_app_picker import FakeStreamlit

    fake_st = FakeStreamlit()
    fake_st.clicked = False
    fake_st.compare_clicked = True
    fake_st.session_state["comparison"] = {"app_name": "stale"}
    fake_st.warnings = []
    monkeypatch.setattr("gui.components.app_picker.st", fake_st)
    monkeypatch.setattr(
        "gui.components.app_picker.load_apps",
        lambda: {
            "cpu_burn": type(
                "App",
                (),
                {"category": "synthetic_cpu", "exe_size_mb": 1.0},
            )()
        },
    )

    class RefusingApi:
        def run_and_compare(self, app_name: str) -> dict[str, Any]:
            raise ApiError(409, "Insufficient available RAM")

    selected, predicted, compared = render_app_picker(RefusingApi())  # type: ignore[arg-type]

    assert (selected, predicted, compared) == ("cpu_burn", False, True)
    assert fake_st.warnings == ["Insufficient available RAM"]
    assert "comparison" not in fake_st.session_state
