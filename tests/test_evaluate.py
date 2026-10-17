"""Tests for model evaluation schemes and metric output."""

import numpy as np

from config import resolve_path
from model.evaluate import evaluate_dataset, evaluate_file
from model.train import load_dataset


def test_both_evaluation_schemes_return_finite_metric_tables() -> None:
    """Both schemes include selected model and baselines with finite metrics."""
    dataframe = load_dataset(
        resolve_path("data", "sample", "sample_dataset.csv")
    )

    chronological, loao, long_results = evaluate_dataset(dataframe, models=["rf"])

    expected_models = {"rf", "persistence", "global_mean"}
    assert set(chronological.index) == expected_models
    assert chronological.shape == (3, 12)
    assert loao.shape == (len(dataframe["app_name"].unique()) * 3 + 3, 12)
    assert np.isfinite(chronological.to_numpy(dtype=float)).all()
    assert np.isfinite(loao.to_numpy(dtype=float)).all()
    assert set(long_results["scheme"]) == {
        "chronological",
        "leave_one_app_out",
        "leave_one_app_out_average",
    }


def test_evaluate_file_writes_markdown_and_csv_reports(tmp_path) -> None:
    """Evaluate a CSV dataset and persist both report formats."""
    output_path = tmp_path / "reports" / "metrics.md"

    evaluate_file(
        resolve_path("data", "sample", "sample_dataset.csv"),
        output_path,
        models=["ridge"],
    )

    assert output_path.is_file()
    assert output_path.with_suffix(".csv").is_file()
    assert "# Model evaluation" in output_path.read_text(encoding="utf-8")
