"""Tests for model-backed predictions."""

import pytest

from errors import UnknownAppError
from model.predict import predict
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
