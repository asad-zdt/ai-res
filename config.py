"""Shared project paths and resource prediction column definitions."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def resolve_path(*parts: str) -> Path:
    """Resolve path components relative to the repository root."""
    return REPO_ROOT.joinpath(*parts)


DATA_DIR = resolve_path("data")
RAW_DATA_DIR = resolve_path("data", "raw")
SAMPLE_DATA_DIR = resolve_path("data", "sample")
PROCESSED_DATA_DIR = resolve_path("data", "processed")
MODEL_DIR = resolve_path("model")
MODEL_ARTIFACTS_DIR = resolve_path("model", "artifacts")
REPORTS_DIR = resolve_path("reports")

FEATURE_COLUMNS = [
    "app_name",
    "app_category",
    "exe_size_mb",
    # Rolling mean of prior runs (leakage-safe)
    "hist_avg_cpu_pct",
    "hist_avg_ram_mb",
    "hist_avg_disk_mbps",
    "hist_avg_net_kbps",
    # Rolling std-dev: captures how predictable each resource is
    "hist_std_cpu_pct",
    "hist_std_ram_mb",
    "hist_std_disk_mbps",
    "hist_std_net_kbps",
    # Rolling min: lower bound of observed usage
    "hist_min_cpu_pct",
    "hist_min_ram_mb",
    "hist_min_disk_mbps",
    "hist_min_net_kbps",
    # Rolling max: upper bound / worst-case usage
    "hist_max_cpu_pct",
    "hist_max_ram_mb",
    "hist_max_disk_mbps",
    "hist_max_net_kbps",
]

TARGET_COLUMNS = ["cpu_pct", "ram_mb", "disk_mbps", "net_kbps"]

API_HOST = "127.0.0.1"
API_PORT = 8000

RAM_MARGIN = 2.0
CPU_MARGIN = 1.5
RESERVE_RAM_MB = 256


if __name__ == "__main__":
    print(f"Repository root: {REPO_ROOT}")
    print(FEATURE_COLUMNS, TARGET_COLUMNS)
