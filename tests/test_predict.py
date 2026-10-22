"""Tests for model-backed predictions."""

import pytest

from errors import UnknownAppError
from model.predict import _load_bundle, predict
from service.mock_predict import mock_predict


def test_mock_predict_returns_copy_of_known_profile() -> None:
    """Return stable resource metrics without exposing shared profile state."""
    first = mock_predict("chrome")
    first["cpu_pct"] = 0.0

    assert mock_predict("chrome")["cpu_pct"] == 45.0


def test_mock_predict_rejects_unknown_app() -> None:
    """Raise the shared unknown-app error for missing mock profiles."""
    with pytest.raises(UnknownAppError, match="Unknown app: unknown_app"):
        mock_predict("unknown_app")


def test_predict_returns_non_negative_metrics() -> None:
    """A known app returns all four non-negative resource metrics."""
    result = predict("cpu_burn")

    assert set(result) == {"cpu_pct", "ram_mb", "disk_mbps", "net_kbps"}
    assert all(isinstance(value, float) and value >= 0 for value in result.values())


def test_predict_unknown_app_raises() -> None:
    """An application absent from the bundle raises UnknownAppError."""
    with pytest.raises(UnknownAppError, match="Unknown app: unknown_app"):
        predict("unknown_app")


def test_model_bundle_cache_refreshes_after_bundle_changes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Load a retrained model when the bundle file changes in place."""
    model_file = tmp_path / "model.pkl"
    model_file.write_bytes(b"old")
    loaded = []
    monkeypatch.setattr(
        "model.predict.joblib.load",
        lambda path: loaded.append(path) or {"generation": len(loaded)},
    )
    first_stat = model_file.stat()

    first = _load_bundle(
        str(model_file), first_stat.st_mtime_ns, first_stat.st_size
    )
    second = _load_bundle(
        str(model_file), first_stat.st_mtime_ns, first_stat.st_size
    )
    model_file.write_bytes(b"new model")
    second_stat = model_file.stat()
    third = _load_bundle(
        str(model_file), second_stat.st_mtime_ns, second_stat.st_size
    )

    assert first is second
    assert first == {"generation": 1}
    assert third == {"generation": 2}
