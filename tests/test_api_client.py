"""Tests for the Streamlit API client without making network requests."""

from typing import Any

import pytest
import requests

from gui.api_client import ApiClient, ApiError, ApiUnreachable


class FakeResponse:
    """Small response stub for API client tests."""

    def __init__(
        self,
        status_code: int = 200,
        body: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body or {}
        self.text = ""

    def json(self) -> dict[str, Any]:
        """Return the configured JSON response."""
        return self._body


class FakeSession:
    """Session stub that records requests and returns a configured response."""

    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        """Record a request and return or raise the configured result."""
        self.calls.append((method, url, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def client() -> tuple[ApiClient, FakeSession]:
    """Create an API client with a fake session."""
    api_client = ApiClient("http://api.example.test/")
    session = FakeSession(FakeResponse(body={"status": "ok"}))
    api_client.session = session  # type: ignore[assignment]
    return api_client, session


def test_successful_predict_posts_app_name_and_timeout(
    client: tuple[ApiClient, FakeSession],
) -> None:
    """Return decoded response data and use the prediction timeout."""
    api_client, session = client
    session.response = FakeResponse(body={"predicted": {"cpu_pct": 12.0}})

    result = api_client.predict("cpu_burn")

    assert result == {"predicted": {"cpu_pct": 12.0}}
    assert session.calls == [
        (
            "POST",
            "http://api.example.test/predict",
            {"timeout": 10, "json": {"app_name": "cpu_burn"}},
        )
    ]


@pytest.mark.parametrize(
    ("status_code", "detail"),
    [
        (404, "Unknown app: missing"),
        (409, "Admission refused"),
        (422, "Invalid app name"),
    ],
)
def test_http_errors_include_status_and_detail(
    client: tuple[ApiClient, FakeSession],
    status_code: int,
    detail: str,
) -> None:
    """Translate non-success responses to ApiError with their detail."""
    api_client, session = client
    session.response = FakeResponse(status_code, {"detail": detail})

    with pytest.raises(ApiError) as error:
        api_client.predict("missing")

    assert error.value.status_code == status_code
    assert str(error.value) == detail


def test_connection_error_maps_to_friendly_unreachable_error(
    client: tuple[ApiClient, FakeSession],
) -> None:
    """Translate connection failures into actionable API-unavailable text."""
    api_client, session = client
    session.response = requests.ConnectionError("connection refused")

    with pytest.raises(ApiUnreachable, match="Is the API running\\?") as error:
        api_client.health()

    assert "uvicorn service.app:app" in str(error.value)


def test_run_and_compare_uses_long_timeout(
    client: tuple[ApiClient, FakeSession],
) -> None:
    """Allow the endpoint enough time to execute the real application."""
    api_client, session = client

    api_client.run_and_compare("cpu_burn")

    assert session.calls[0][2]["timeout"] == 180
