"""Generate a reproducible synthetic resource-usage dataset."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Enable direct execution from this nested directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import FEATURE_COLUMNS, TARGET_COLUMNS, resolve_path


def app_profiles() -> dict[str, tuple[str, float, tuple[float, float, float, float]]]:
    """Return each sample application's category, executable size, and target profile."""
    return {
        "chrome": ("browser", 250.0, (45.0, 900.0, 1.5, 220.0)),
        "firefox": ("browser", 190.0, (38.0, 750.0, 1.2, 180.0)),
        "vscode": ("editor", 130.0, (22.0, 520.0, 0.8, 90.0)),
        "gedit": ("editor", 8.0, (3.0, 120.0, 0.1, 5.0)),
        "ffmpeg": ("media", 45.0, (180.0, 400.0, 18.0, 0.0)),
        "python_script": ("script", 0.2, (35.0, 250.0, 2.0, 15.0)),
        "gcc_build": ("compiler", 30.0, (250.0, 1500.0, 8.0, 10.0)),
        "vlc": ("media", 55.0, (28.0, 350.0, 3.0, 120.0)),
    }


def generate_dataset(seed: int = 42) -> pd.DataFrame:
    """Build 40 synthetic runs with rolling per-app historical features."""
    rng = np.random.default_rng(seed)
    records: list[dict[str, object]] = []

    for app_name, (category, exe_size_mb, profile) in app_profiles().items():
        prior_targets: list[np.ndarray] = []
        base = np.asarray(profile, dtype=float)

        for run_index in range(5):
            if prior_targets:
                history_arr = np.asarray(prior_targets)
                history_mean = np.mean(history_arr, axis=0)
                history_std = np.std(history_arr, axis=0, ddof=1) if len(prior_targets) >= 2 else np.zeros(4)
                history_min = np.min(history_arr, axis=0)
                history_max = np.max(history_arr, axis=0)
            else:
                history_mean = np.maximum(0.0, base * (1.0 + rng.normal(0.0, 0.05, 4)))
                history_std = np.zeros(4)
                history_min = history_mean.copy()
                history_max = history_mean.copy()

            targets = np.maximum(0.0, base * (1.0 + rng.normal(0.0, 0.15, 4)))
            record: dict[str, object] = {
                "app_name": app_name,
                "app_category": category,
                "exe_size_mb": exe_size_mb,
                "hist_avg_cpu_pct": history_mean[0],
                "hist_avg_ram_mb": history_mean[1],
                "hist_avg_disk_mbps": history_mean[2],
                "hist_avg_net_kbps": history_mean[3],
                "hist_std_cpu_pct": history_std[0],
                "hist_std_ram_mb": history_std[1],
                "hist_std_disk_mbps": history_std[2],
                "hist_std_net_kbps": history_std[3],
                "hist_min_cpu_pct": history_min[0],
                "hist_min_ram_mb": history_min[1],
                "hist_min_disk_mbps": history_min[2],
                "hist_min_net_kbps": history_min[3],
                "hist_max_cpu_pct": history_max[0],
                "hist_max_ram_mb": history_max[1],
                "hist_max_disk_mbps": history_max[2],
                "hist_max_net_kbps": history_max[3],
            }
            record.update(dict(zip(TARGET_COLUMNS, targets, strict=True)))
            records.append(record)
            prior_targets.append(targets)

    dataframe = pd.DataFrame(records, columns=FEATURE_COLUMNS + TARGET_COLUMNS)
    numeric_columns = dataframe.select_dtypes(include="number").columns
    dataframe[numeric_columns] = dataframe[numeric_columns].clip(lower=0).round(2)
    return dataframe


def main() -> None:
    """Generate the CSV in the repository's sample-data directory."""
    output_path = resolve_path("data", "sample", "sample_dataset.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = generate_dataset()
    dataframe.to_csv(output_path, index=False)
    print(dataframe.groupby("app_name").mean(numeric_only=True))
    print(dataframe.isna().sum().sum())


if __name__ == "__main__":
    main()
