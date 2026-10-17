"""Tests for the prediction API."""

import pytest
from fastapi.testclient import TestClient

from errors import UnknownAppError
from service.app import app

client = TestClient(app)
_METRICS = {
    "cpu_pct": 1.0,
    "ram_mb": 2.0,
    "disk_mbps": 3.0,
    "net_kbps": 4.0,
}


def test_health_reports_active_predictor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expose a successful health response and the selected predictor."""
    monkeypatch.setattr("service.app._active_predictor", lambda: "model")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "predictor": "model"}


@pytest.mark.parametrize("predictor", ["mock", "model"])
def test_predict_returns_all_resource_metrics(
    predictor: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both predictors return metrics for configured applications."""
    monkeypatch.setenv("PREDICTOR", predictor)
    monkeypatch.setattr("service.app.mock_predict", lambda app_name: _METRICS)
    monkeypatch.setattr("service.app.model_predict", lambda app_name: _METRICS)
    response = client.post("/predict", json={"app_name": "cpu_burn"})

    assert response.status_code == 200
    assert response.json()["app_name"] == "cpu_burn"
    assert set(response.json()["predicted"]) == set(_METRICS)
    assert response.json()["source"] == predictor


@pytest.mark.parametrize("predictor", ["mock", "model"])
def test_predict_unknown_app_returns_404(
    predictor: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apps absent from the YAML registry return the contract's 404."""
    monkeypatch.setenv("PREDICTOR", predictor)
    response = client.post("/predict", json={"app_name": "unknown_app"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown app: unknown_app"}


@pytest.mark.parametrize("predictor", ["mock", "model"])
def test_predict_configured_app_without_profile_returns_503(
    predictor: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configured apps without predictor profiles are reported as unavailable."""
    monkeypatch.setenv("PREDICTOR", predictor)

    def missing_profile(app_name: str) -> dict[str, float]:
        raise UnknownAppError(app_name)

    monkeypatch.setattr("service.app.mock_predict", missing_profile)
    monkeypatch.setattr("service.app.model_predict", missing_profile)
    response = client.post("/predict", json={"app_name": "cpu_burn"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "No prediction profile available for configured app: cpu_burn"
    }


@pytest.mark.parametrize("predictor", ["mock", "model"])
def test_predict_invalid_name_returns_422(
    predictor: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both predictors reject an invalid application identifier."""
    monkeypatch.setenv("PREDICTOR", predictor)
    response = client.post("/predict", json={"app_name": "chrome!"})

    assert response.status_code == 422
