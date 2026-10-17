"""Compare resource predictors with chronological and unseen-app evaluations."""

import argparse
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from config import FEATURE_COLUMNS, TARGET_COLUMNS, resolve_path
from model.train import build_model_pipeline, load_dataset

_HISTORY_COLUMNS = {
    "cpu_pct": "hist_avg_cpu_pct",
    "ram_mb": "hist_avg_ram_mb",
    "disk_mbps": "hist_avg_disk_mbps",
    "net_kbps": "hist_avg_net_kbps",
}
_BASELINES = ("persistence", "global_mean")
_METRICS = ("MAE", "RMSE", "MAE%")


def _eligible_apps(dataframe: pd.DataFrame) -> list[str]:
    """Return apps with at least three rows and warn about skipped apps."""
    counts = dataframe["app_name"].value_counts()
    skipped = counts[counts < 3]
    for app_name, count in skipped.items():
        warnings.warn(
            f"Skipping app {app_name!r}: only {count} row(s); at least 3 required",
            RuntimeWarning,
            stacklevel=2,
        )
    return [str(app_name) for app_name in counts[counts >= 3].index]


def _metrics_for_predictions(
    actual: pd.DataFrame,
    predicted: np.ndarray,
) -> dict[str, dict[str, float]]:
    """Calculate MAE, RMSE, and normalized MAE for every target."""
    result: dict[str, dict[str, float]] = {}
    for index, target in enumerate(TARGET_COLUMNS):
        expected = actual[target].to_numpy(dtype=float)
        estimates = np.asarray(predicted[:, index], dtype=float)
        mae = float(mean_absolute_error(expected, estimates))
        rmse = float(np.sqrt(mean_squared_error(expected, estimates)))
        mean_target = float(np.mean(expected))
        mae_pct = mae / mean_target * 100.0 if mean_target != 0 else 0.0
        result[target] = {"MAE": mae, "RMSE": rmse, "MAE%": mae_pct}
    return result


def _predictions_for_model(
    model_name: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> np.ndarray:
    """Fit a selected estimator on training rows and predict test rows."""
    pipeline = build_model_pipeline(model_name)
    pipeline.fit(train[FEATURE_COLUMNS], train[TARGET_COLUMNS])
    return np.asarray(pipeline.predict(test[FEATURE_COLUMNS]), dtype=float)


def _predictions_for_baseline(
    model_name: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> np.ndarray:
    """Create persistence or training-target global-mean predictions."""
    if model_name == "persistence":
        return test[
            [_HISTORY_COLUMNS[target] for target in TARGET_COLUMNS]
        ].to_numpy(dtype=float)
    means = train[TARGET_COLUMNS].mean(axis=0).to_numpy(dtype=float)
    return np.tile(means, (len(test), 1))


def _evaluate_split(
    train: pd.DataFrame,
    test: pd.DataFrame,
    models: list[str],
) -> dict[str, dict[str, dict[str, float]]]:
    """Evaluate requested estimators and standard baselines on one split."""
    results: dict[str, dict[str, dict[str, float]]] = {}
    for model_name in (*models, *_BASELINES):
        if model_name in _BASELINES:
            predictions = _predictions_for_baseline(model_name, train, test)
        else:
            predictions = _predictions_for_model(model_name, train, test)
        results[model_name] = _metrics_for_predictions(
            test[TARGET_COLUMNS],
            predictions,
        )
    return results


def _to_long_rows(
    scheme: str,
    app_name: str,
    results: dict[str, dict[str, dict[str, float]]],
) -> list[dict[str, Any]]:
    """Convert metric results into the report's long-form rows."""
    return [
        {
            "scheme": scheme,
            "app_name": app_name,
            "model": model_name,
            "target": target,
            **metrics,
        }
        for model_name, target_metrics in results.items()
        for target, metrics in target_metrics.items()
    ]


def _wide_table(
    results: dict[str, dict[str, dict[str, float]]],
) -> pd.DataFrame:
    """Build a display table with target/metric multi-level columns."""
    columns = pd.MultiIndex.from_product(
        [TARGET_COLUMNS, _METRICS],
        names=("target", "metric"),
    )
    rows = {
        model_name: [
            target_metrics[target][metric]
            for target in TARGET_COLUMNS
            for metric in _METRICS
        ]
        for model_name, target_metrics in results.items()
    }
    return pd.DataFrame.from_dict(rows, orient="index", columns=columns)


def evaluate_dataset(
    dataframe: pd.DataFrame,
    models: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run chronological and leave-one-app-out schemes and return their tables."""
    selected_models = models or ["rf"]
    supported_models = {"rf", "gbr", "ridge"}
    invalid_models = sorted(set(selected_models) - supported_models)
    if invalid_models:
        raise ValueError(f"Unsupported models: {invalid_models}")

    eligible = _eligible_apps(dataframe)
    working = dataframe.loc[dataframe["app_name"].isin(eligible)].copy()
    working = working.sort_values(["app_name"], kind="stable")
    if not eligible:
        raise ValueError("Evaluation requires at least one app with 3 or more rows")

    chronological_train: list[pd.DataFrame] = []
    chronological_test: list[pd.DataFrame] = []
    for _, group in working.groupby("app_name", sort=False):
        ordered = group.sort_values(
            ["timestamp"] if "timestamp" in group.columns else [],
            kind="stable",
        )
        chronological_train.append(ordered.iloc[:-2])
        chronological_test.append(ordered.iloc[-2:])
    train = pd.concat(chronological_train)
    test = pd.concat(chronological_test)
    if train.empty or test.empty:
        raise ValueError("Chronological evaluation needs non-empty train and test sets")
    chronological_results = _evaluate_split(train, test, selected_models)
    chronological_table = _wide_table(chronological_results)
    long_rows = _to_long_rows("chronological", "", chronological_results)

    loao_results: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for app_name in eligible:
        app_test = working.loc[working["app_name"] == app_name]
        app_train = working.loc[working["app_name"] != app_name]
        if app_train.empty:
            warnings.warn(
                f"Skipping leave-one-app-out for {app_name!r}: no other apps to train on",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        results = _evaluate_split(app_train, app_test, selected_models)
        loao_results[app_name] = results
        long_rows.extend(_to_long_rows("leave_one_app_out", app_name, results))

    average_results: dict[str, dict[str, dict[str, float]]] = {}
    if loao_results:
        all_models = (*selected_models, *_BASELINES)
        for model_name in all_models:
            average_results[model_name] = {}
            for target in TARGET_COLUMNS:
                average_results[model_name][target] = {
                    metric: float(
                        np.mean(
                            [
                                loao_results[app_name][model_name][target][metric]
                                for app_name in loao_results
                            ]
                        )
                    )
                    for metric in _METRICS
                }
        long_rows.extend(
            _to_long_rows("leave_one_app_out_average", "AVERAGE", average_results)
        )

    loao_rows: dict[str, list[float]] = {}
    for app_name, results in loao_results.items():
        for model_name, target_metrics in results.items():
            loao_rows[f"{app_name} / {model_name}"] = [
                target_metrics[target][metric]
                for target in TARGET_COLUMNS
                for metric in _METRICS
            ]
    for model_name, target_metrics in average_results.items():
        loao_rows[f"AVERAGE / {model_name}"] = [
            target_metrics[target][metric]
            for target in TARGET_COLUMNS
            for metric in _METRICS
        ]
    loao_columns = pd.MultiIndex.from_product(
        [TARGET_COLUMNS, _METRICS],
        names=("target", "metric"),
    )
    loao_table = pd.DataFrame.from_dict(
        loao_rows,
        orient="index",
        columns=loao_columns,
    )
    return chronological_table, loao_table, pd.DataFrame(long_rows)


def _format_markdown_table(table: pd.DataFrame) -> str:
    """Format a multi-index metric table as a Markdown table."""
    headers = ["model / app", *(f"{target} {metric}" for target, metric in table.columns)]
    rows = [
        [str(index), *(f"{value:.4f}" for value in row)]
        for index, row in zip(table.index, table.to_numpy(), strict=True)
    ]
    widths = [
        max([len(headers[column]), *(len(row[column]) for row in rows)])
        for column in range(len(headers))
    ]
    header_line = "| " + " | ".join(
        header.ljust(widths[index]) for index, header in enumerate(headers)
    ) + " |"
    separator = "| " + " | ".join("-" * width for width in widths) + " |"
    body = [
        "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
        for row in rows
    ]
    return "\n".join([header_line, separator, *body])


def evaluate_file(
    data_path: Path,
    markdown_path: Path,
    models: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Evaluate a CSV and write Markdown and long-format CSV reports."""
    dataframe = load_dataset(data_path)
    chronological, loao, long_results = evaluate_dataset(dataframe, models=models)

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = (
        "# Model evaluation\n\n"
        "## Chronological holdout\n\n"
        f"{_format_markdown_table(chronological)}\n\n"
        "## Leave-one-app-out (per-app and unweighted average)\n\n"
        f"{_format_markdown_table(loao)}\n"
    )
    markdown_path.write_text(markdown, encoding="utf-8")

    csv_path = markdown_path.with_suffix(".csv")
    long_results.to_csv(csv_path, index=False)
    print("Chronological holdout")
    print(_format_markdown_table(chronological))
    print("\nLeave-one-app-out (per-app and average)")
    print(_format_markdown_table(loao))
    print(f"\nMarkdown report: {markdown_path}")
    print(f"CSV report: {csv_path}")
    return chronological, loao, long_results


def _resolve_path(path: str) -> Path:
    """Resolve a CLI path relative to the repository root unless absolute."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else resolve_path(path)


def main() -> None:
    """Parse arguments and run model evaluation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/processed/dataset.csv")
    parser.add_argument("--out", default="reports/evaluation_metrics.md")
    parser.add_argument(
        "--models",
        default="rf",
        help="Comma-separated model choices: rf,gbr,ridge",
    )
    args = parser.parse_args()
    models = [model.strip() for model in args.models.split(",") if model.strip()]
    if not models:
        parser.error("--models must include at least one of rf, gbr, ridge")
    try:
        evaluate_file(_resolve_path(args.data), _resolve_path(args.out), models)
    except (FileNotFoundError, ValueError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
