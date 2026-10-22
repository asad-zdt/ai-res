"""Deterministic mock resource predictions for known applications.

Covers both the sample-dataset apps and every workload in apps_config.yaml so
that the API always returns a prediction even when a trained model bundle has no
profile for a configured app.
"""

from errors import UnknownAppError

_PROFILES: dict[str, dict[str, float]] = {
    # ── Sample-dataset apps ──────────────────────────────────────────────────
    "chrome": {
        "cpu_pct": 45.0,
        "ram_mb": 900.0,
        "disk_mbps": 1.5,
        "net_kbps": 220.0,
    },
    "firefox": {
        "cpu_pct": 38.0,
        "ram_mb": 750.0,
        "disk_mbps": 1.2,
        "net_kbps": 180.0,
    },
    "vscode": {
        "cpu_pct": 22.0,
        "ram_mb": 520.0,
        "disk_mbps": 0.8,
        "net_kbps": 90.0,
    },
    "gedit": {
        "cpu_pct": 3.0,
        "ram_mb": 120.0,
        "disk_mbps": 0.1,
        "net_kbps": 5.0,
    },
    "ffmpeg": {
        "cpu_pct": 180.0,
        "ram_mb": 400.0,
        "disk_mbps": 18.0,
        "net_kbps": 0.0,
    },
    "python_script": {
        "cpu_pct": 35.0,
        "ram_mb": 250.0,
        "disk_mbps": 2.0,
        "net_kbps": 15.0,
    },
    "gcc_build": {
        "cpu_pct": 250.0,
        "ram_mb": 1500.0,
        "disk_mbps": 8.0,
        "net_kbps": 10.0,
    },
    "vlc": {
        "cpu_pct": 28.0,
        "ram_mb": 350.0,
        "disk_mbps": 3.0,
        "net_kbps": 120.0,
    },
    # ── Collector workloads (apps_config.yaml) ───────────────────────────────
    "cpu_burn": {
        "cpu_pct": 200.0,   # multi-worker Python burn
        "ram_mb": 80.0,
        "disk_mbps": 0.0,
        "net_kbps": 0.0,
    },
    "mem_hog": {
        "cpu_pct": 5.0,
        "ram_mb": 300.0,    # mid-point of 128/256/512 MB variants
        "disk_mbps": 0.0,
        "net_kbps": 0.0,
    },
    "disk_writer": {
        "cpu_pct": 15.0,
        "ram_mb": 60.0,
        "disk_mbps": 200.0,  # sequential write benchmark
        "net_kbps": 0.0,
    },
    "sort_big": {
        "cpu_pct": 90.0,
        "ram_mb": 400.0,
        "disk_mbps": 30.0,
        "net_kbps": 0.0,
    },
    "compile_build": {
        "cpu_pct": 180.0,
        "ram_mb": 300.0,
        "disk_mbps": 10.0,
        "net_kbps": 0.0,
    },
    "ffmpeg_encode": {
        "cpu_pct": 150.0,
        "ram_mb": 200.0,
        "disk_mbps": 15.0,
        "net_kbps": 0.0,
    },
    "curl_download": {
        "cpu_pct": 5.0,
        "ram_mb": 30.0,
        "disk_mbps": 0.5,
        "net_kbps": 8000.0,   # ~8 MB/s download
    },
    "edge_headless": {
        "cpu_pct": 40.0,
        "ram_mb": 600.0,
        "disk_mbps": 2.0,
        "net_kbps": 500.0,
    },
}


def mock_predict(app_name: str) -> dict[str, float]:
    """Return a deterministic resource profile for a known application.

    Raises UnknownAppError if the app has no profile, so the API can surface
    a clear 503 rather than a confusing KeyError.
    """
    profile = _PROFILES.get(app_name)
    if profile is None:
        raise UnknownAppError(app_name)
    return profile.copy()
