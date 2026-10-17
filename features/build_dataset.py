"""Build leakage-safe training data and serving profiles from collected runs."""

import argparse
from pathlib import Path

import pandas as pd

from config import FEATURE_COLUMNS, TARGET_COLUMNS, resolve_path
from features.feature_schema import validate_frame

_RUN_COLUMNS = [
    "app_name",
    "app_category",
    "exe_size_mb",
    "timestamp",
    "valid",
    *TARGET_COLUMNS,
]
_HISTORY_COLUMNS = {
    "cpu_pct": "hist_avg_cpu_pct",
    "ram_mb": "hist_avg_ram_mb",
    "disk_mbps": "hist_avg_disk_mbps",
    "net_kbps": "hist_avg_net_kbps",
}


def prepare_datasets(
    runs: pd.DataFrame, window: int = 5
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Create training rows and latest serving profiles from raw run records."""
    if isinstance(window, bool) or window < 1:
        raise ValueError("window must be a positive integer")
    if not isinstance(window, int):
        raise ValueError("window must be a positive integer")

    missing_columns = [column for column in _RUN_COLUMNS if column not in runs]
    if missing_columns:
        raise ValueError(f"Runs dataframe is missing required columns: {missing_columns}")

    valid_runs = runs.loc[runs["valid"].eq(True)].copy()
    valid_runs = valid_runs.sort_values(
        ["app_name", "timestamp"], kind="stable"
    ).reset_index(drop=True)

    # Shift each target before rolling so the current run never contributes to its own history.
    histories = valid_runs.groupby("app_name", sort=False)[TARGET_COLUMNS].transform(
        lambda values: values.shift(1).rolling(window=window, min_periods=1).mean()
    )
    for target, history_column in _HISTORY_COLUMNS.items():
        valid_runs[history_column] = histories[target]

    first_run_mask = valid_runs["hist_avg_cpu_pct"].isna()
    dropped_rows = int(first_run_mask.sum())
    training = valid_runs.loc[~first_run_mask].copy()
    training = training[FEATURE_COLUMNS + TARGET_COLUMNS].reset_index(drop=True)
    validate_frame(training)

    latest_window = valid_runs.groupby("app_name", sort=False, group_keys=False).tail(
        window
    )
    profiles = latest_window.groupby("app_name", sort=False).agg(
        app_category=("app_category", "last"),
        exe_size_mb=("exe_size_mb", "last"),
        **{
            _HISTORY_COLUMNS[target]: (target, "mean")
            for target in TARGET_COLUMNS
        },
    )
    profiles = profiles.reset_index()[
        [
            "app_name",
            "app_category",
            "exe_size_mb",
            _HISTORY_COLUMNS["cpu_pct"],
            _HISTORY_COLUMNS["ram_mb"],
            _HISTORY_COLUMNS["disk_mbps"],
            _HISTORY_COLUMNS["net_kbps"],
        ]
    ]
    return training, profiles, dropped_rows


def build_dataset(
    runs_path: Path,
    output_path: Path,
    window: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Read raw runs, build both datasets, and save their CSV files."""
    runs = pd.read_csv(runs_path)
    training, profiles, dropped_rows = prepare_datasets(runs, window=window)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    training.to_csv(output_path, index=False)

    profile_path = output_path.parent / "app_profiles.csv"
    profiles.to_csv(profile_path, index=False)
    return training, profiles, dropped_rows


def _resolve_path(path: str) -> Path:
    """Resolve a CLI path relative to the repository root unless absolute."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else resolve_path(path)


def main() -> None:
    """Parse CLI arguments, build the datasets, and print a compact summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", default="data/raw/runs.csv")
    parser.add_argument("--out", default="data/processed/dataset.csv")
    parser.add_argument("--window", type=int, default=5)
    args = parser.parse_args()
    if args.window < 1:
        parser.error("--window must be a positive integer")

    try:
        training, profiles, dropped_rows = build_dataset(
            _resolve_path(args.runs),
            _resolve_path(args.out),
            window=args.window,
        )
    except (FileNotFoundError, ValueError) as error:
        parser.exit(2, f"Error: {error}\n")

    print(f"Dropped first runs without history: {dropped_rows}")
    print("Rows per app:")
    print(training.groupby("app_name").size().to_string())
    print("Target summary:")
    print(training[TARGET_COLUMNS].describe().to_string())
    print(f"Training rows: {len(training)}")
    print(f"Serving profiles: {len(profiles)}")


if __name__ == "__main__":
    main()
