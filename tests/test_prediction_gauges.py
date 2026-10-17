"""Tests for prediction gauge scales and figures."""

import pandas as pd
import pytest

from gui.components import prediction_gauges


def test_disk_and_network_scales_use_processed_dataset(
    tmp_path,
    monkeypatch,
) -> None:
    """Scale gauges to 1.5 times each processed target maximum."""
    processed = tmp_path / "processed.csv"
    sample = tmp_path / "sample.csv"
    pd.DataFrame(
        {"disk_mbps": [2.0, 4.0], "net_kbps": [100.0, 200.0]}
    ).to_csv(processed, index=False)
    pd.DataFrame(
        {"disk_mbps": [100.0], "net_kbps": [1000.0]}
    ).to_csv(sample, index=False)
    monkeypatch.setattr(
        prediction_gauges,
        "resolve_path",
        lambda *parts: processed if parts[1] == "processed" else sample,
    )
    prediction_gauges._disk_network_scales.clear()

    assert prediction_gauges._disk_network_scales() == {
        "disk_mbps": 6.0,
        "net_kbps": 300.0,
    }


def test_disk_and_network_scales_fall_back_to_sample_dataset(
    tmp_path,
    monkeypatch,
) -> None:
    """Use sample data if the processed dataset cannot be read."""
    sample = tmp_path / "sample.csv"
    pd.DataFrame({"disk_mbps": [3.0], "net_kbps": [80.0]}).to_csv(
        sample,
        index=False,
    )
    monkeypatch.setattr(
        prediction_gauges,
        "resolve_path",
        lambda *parts: tmp_path / "missing.csv" if parts[1] == "processed" else sample,
    )
    prediction_gauges._disk_network_scales.clear()

    assert prediction_gauges._disk_network_scales() == {
        "disk_mbps": 4.5,
        "net_kbps": 120.0,
    }


def test_gauge_figure_has_transparent_background_and_scale_range() -> None:
    """Build a readable theme-neutral Plotly gauge with the requested bounds."""
    figure = prediction_gauges._gauge_figure("CPU", 25.0, "%", 400.0)
    gauge = figure.data[0].gauge

    assert figure.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert list(gauge.axis.range) == [0, 400.0]
    assert [step.range[1] for step in gauge.steps] == [200.0, 320.0, 400.0]


def test_render_prediction_gauges_draws_all_resource_metrics(monkeypatch) -> None:
    """Render one Plotly gauge and scale caption for each resource metric."""

    class FakeColumn:
        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback):
            return False

    figures = []
    captions = []
    monkeypatch.setattr(
        prediction_gauges.st,
        "columns",
        lambda count: [FakeColumn() for _ in range(count)],
    )
    monkeypatch.setattr(
        prediction_gauges.st,
        "plotly_chart",
        lambda figure, **kwargs: figures.append(figure),
    )
    monkeypatch.setattr(prediction_gauges.st, "caption", captions.append)
    monkeypatch.setattr(
        prediction_gauges,
        "_system_scales",
        lambda: {"cpu_pct": 200.0, "ram_mb": 8000.0},
    )
    monkeypatch.setattr(
        prediction_gauges,
        "_disk_network_scales",
        lambda: {"disk_mbps": 10.0, "net_kbps": 1000.0},
    )

    prediction_gauges.render_prediction_gauges(
        {"cpu_pct": 10, "ram_mb": 100, "disk_mbps": 2, "net_kbps": 50}
    )

    assert len(figures) == 4
    assert len(captions) == 4


def test_render_prediction_gauges_rejects_negative_metric(monkeypatch) -> None:
    """Reject an invalid resource metric before rendering its gauge."""
    monkeypatch.setattr(
        prediction_gauges,
        "_system_scales",
        lambda: {"cpu_pct": 200.0, "ram_mb": 8000.0},
    )
    monkeypatch.setattr(
        prediction_gauges,
        "_disk_network_scales",
        lambda: {"disk_mbps": 10.0, "net_kbps": 1000.0},
    )

    with pytest.raises(ValueError, match="cannot be negative"):
        prediction_gauges.render_prediction_gauges(
            {"cpu_pct": -1, "ram_mb": 100, "disk_mbps": 2, "net_kbps": 50}
        )
