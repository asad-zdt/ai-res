"""Tests for model training and bundle persistence."""

from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.multioutput import MultiOutputRegressor
from sklearn.preprocessing import StandardScaler

from config import resolve_path
from model.train import (
    build_model_pipeline,
    chronological_split,
    train_and_save,
)


def test_train_saves_bundle(tmp_path: Path) -> None:
    """Train from the sample CSV and save a bundle with the required fields."""
    output_path = tmp_path / "nested" / "model.pkl"

    bundle = train_and_save(
        resolve_path("data", "sample", "sample_dataset.csv"),
        output_path,
    )
    saved_bundle = joblib.load(output_path)

    expected_keys = {
        "pipeline",
        "feature_columns",
        "target_columns",
        "app_profiles",
        "trained_at",
        "n_rows",
    }
    assert set(bundle) == expected_keys
    assert set(saved_bundle) == expected_keys
    assert saved_bundle["n_rows"] == 40
    assert set(saved_bundle["app_profiles"]) == {
        "chrome",
        "firefox",
        "vscode",
        "gedit",
        "ffmpeg",
        "python_script",
        "gcc_build",
        "vlc",
    }


def test_chronological_split_holds_out_each_app_tail() -> None:
    """Hold out the last row from each five-row app history."""
    dataframe = pd.DataFrame(
        {
            "app_name": ["alpha"] * 5 + ["beta"] * 5,
            "run_number": list(range(5)) * 2,
        }
    )

    train_indices, test_indices = chronological_split(dataframe)

    assert list(test_indices) == [4, 9]
    assert list(train_indices) == [0, 1, 2, 3, 5, 6, 7, 8]


def test_model_choices_use_expected_estimators() -> None:
    """Construct each supported model with its required estimator/scaler."""
    assert isinstance(
        build_model_pipeline("rf").named_steps["regressor"],
        RandomForestRegressor,
    )
    gbr_pipeline = build_model_pipeline("gbr")
    assert isinstance(gbr_pipeline.named_steps["regressor"], MultiOutputRegressor)
    assert isinstance(
        gbr_pipeline.named_steps["regressor"].estimator,
        GradientBoostingRegressor,
    )
    ridge_pipeline = build_model_pipeline("ridge")
    assert isinstance(ridge_pipeline.named_steps["scaler"], StandardScaler)
    assert isinstance(ridge_pipeline.named_steps["regressor"], MultiOutputRegressor)
    assert isinstance(ridge_pipeline.named_steps["regressor"].estimator, Ridge)


def test_train_uses_sibling_serving_profiles(tmp_path: Path) -> None:
    """Prefer app_profiles.csv over the latest training feature row."""
    sample_path = resolve_path("data", "sample", "sample_dataset.csv")
    dataframe = pd.read_csv(sample_path)
    dataset_path = tmp_path / "dataset.csv"
    dataframe.to_csv(dataset_path, index=False)
    profiles_path = tmp_path / "app_profiles.csv"
    profiles = pd.DataFrame(
        [
            {
                "app_name": name,
                "app_category": "serving_category",
                "exe_size_mb": 999.0,
                "hist_avg_cpu_pct": 8.0,
                "hist_avg_ram_mb": 9.0,
                "hist_avg_disk_mbps": 10.0,
                "hist_avg_net_kbps": 11.0,
            }
            for name in dataframe["app_name"].unique()
        ]
    )
    profiles.to_csv(profiles_path, index=False)

    bundle = train_and_save(dataset_path, tmp_path / "model.pkl")

    assert bundle["app_profiles"]["chrome"] == {
        "app_category": "serving_category",
        "exe_size_mb": 999.0,
        "hist_avg_cpu_pct": 8.0,
        "hist_avg_ram_mb": 9.0,
        "hist_avg_disk_mbps": 10.0,
        "hist_avg_net_kbps": 11.0,
    }
