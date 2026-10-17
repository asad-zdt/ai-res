"""Deterministic mock resource predictions for the sample applications."""

from errors import UnknownAppError

_PROFILES: dict[str, dict[str, float]] = {
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
}


def mock_predict(app_name: str) -> dict[str, float]:
    """Return a deterministic resource profile for a known sample application."""
    try:
        profile = _PROFILES[app_name]
    except KeyError:
        raise UnknownAppError(app_name) from None
    return profile.copy()
