"""Tests for leakage-safe feature and serving-profile generation."""

import pandas as pd
import pytest

from config import FEATURE_COLUMNS, TARGET_COLUMNS
from features.build_dataset import build_dataset, prepare_datasets
from features.feature_schema import validate_frame


def _runs_frame() -> pd.DataFrame:
    """Create a small chronological dataset with one invalid run."""
    rows = []
    metric_values = [10.0, 20.0, 40.0, 1000.0]
    for index, cpu_value in enumerate(metric_values):
        rows.append(
            {
                "app_name": "demo",
                "app_category": "test",
                "exe_size_mb": 2.0,
                "timestamp": f"2026-01-0{index + 1}T00:00:00",
                "valid": index != 3,
                "cpu_pct": cpu_value,
                "ram_mb": cpu_value + 1,
                "disk_mbps": cpu_value + 2,
                "net_kbps": cpu_value + 3,
            }
        )
    rows.extend(
        [
            {
                "app_name": "other",
                "app_category": "test",
                "exe_size_mb": 1.0,
                "timestamp": "2026-01-01T00:00:00",
                "valid": True,
                "cpu_pct": 5.0,
                "ram_mb": 6.0,
                "disk_mbps": 7.0,
                "net_kbps": 8.0,
            },
            {
                "app_name": "other",
                "app_category": "test",
                "exe_size_mb": 1.0,
                "timestamp": "2026-01-02T00:00:00",
                "valid": True,
                "cpu_pct": 7.0,
                "ram_mb": 8.0,
                "disk_mbps": 9.0,
                "net_kbps": 10.0,
            },
        ]
    )
    return pd.DataFrame(rows)


def test_history_excludes_current_target_and_drops_first_runs() -> None:
    """A third run sees only the first two valid targets in its history."""
    training, profiles, dropped_rows = prepare_datasets(_runs_frame(), window=5)

    demo_rows = training.loc[training["app_name"] == "demo"]
    assert len(demo_rows) == 2
    expected_history = {
        "hist_avg_cpu_pct": 15.0,
        "hist_avg_ram_mb": 16.0,
        "hist_avg_disk_mbps": 17.0,
        "hist_avg_net_kbps": 18.0,
    }
    for history, expected in expected_history.items():
        assert demo_rows.iloc[1][history] == expected
    assert demo_rows.iloc[1]["cpu_pct"] == 40.0
    assert dropped_rows == 2
    assert list(training.columns) == FEATURE_COLUMNS + TARGET_COLUMNS
    assert "1000.0" not in training["cpu_pct"].astype(str).tolist()
    assert set(profiles["app_name"]) == {"demo", "other"}


def test_invalid_runs_are_excluded() -> None:
    """Invalid runs do not become targets or contribute to historical means."""
    training, _, _ = prepare_datasets(_runs_frame(), window=5)

    assert 1000.0 not in training["cpu_pct"].tolist()
    assert training.loc[
        (training["app_name"] == "demo") & (training["cpu_pct"] == 40.0),
        "hist_avg_cpu_pct",
    ].item() == 15.0


def test_build_dataset_writes_training_data_and_profiles(tmp_path) -> None:
    """Write training and serving CSVs to the requested output directory."""
    runs_path = tmp_path / "runs.csv"
    output_path = tmp_path / "processed" / "dataset.csv"
    _runs_frame().to_csv(runs_path, index=False)

    training, profiles, dropped_rows = build_dataset(runs_path, output_path)

    assert output_path.is_file()
    assert (output_path.parent / "app_profiles.csv").is_file()
    assert len(pd.read_csv(output_path)) == len(training)
    assert len(pd.read_csv(output_path.parent / "app_profiles.csv")) == len(profiles)
    assert dropped_rows == 2


def test_validate_frame_reports_missing_columns() -> None:
    """Validation identifies missing required schema columns."""
    with pytest.raises(ValueError, match="missing required columns"):
        validate_frame(pd.DataFrame(columns=FEATURE_COLUMNS))
