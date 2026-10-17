"""HTTP client for the resource-allocation API."""

import os
from typing import Any

import requests


class ApiError(RuntimeError):
    """An API response error with its HTTP status code."""

    def __init__(self, status_code: int, message: str) -> None:
        """Create an API error from its HTTP status and detail message."""
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class ApiUnreachable(RuntimeError):
    """The API could not be reached before connection or request timeout."""


class ApiClient:
    """Call resource-allocation endpoints using a reusable HTTP session."""

    def __init__(self, base_url: str | None = None) -> None:
        """Initialize the API URL from an argument or the ``API_URL`` env var."""
        self.base_url = (
            base_url or os.environ.get("API_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        self.session = requests.Session()

    def health(self) -> dict[str, Any]:
        """Return API health and active predictor information."""
        return self._request("GET", "/health", timeout=10)

    def predict(self, app_name: str) -> dict[str, Any]:
        """Return a resource prediction for an application."""
        return self._request(
            "POST",
            "/predict",
            timeout=10,
            json={"app_name": app_name},
        )

    def run_and_compare(self, app_name: str) -> dict[str, Any]:
        """Run an application and return its prediction-versus-actual result."""
        return self._request(
            "POST",
            "/run-and-compare",
            timeout=180,
            json={"app_name": app_name},
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        timeout: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a request and translate transport or HTTP failures."""
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{endpoint}",
                timeout=timeout,
                **kwargs,
            )
        except (requests.ConnectionError, requests.Timeout) as error:
            raise ApiUnreachable(
                "Could not reach the API. Is the API running? Start it with "
                "`uvicorn service.app:app --host 127.0.0.1 --port 8000`."
            ) from error

        if not 200 <= response.status_code < 300:
            detail = _response_detail(response)
            raise ApiError(response.status_code, detail)
        return response.json()


def _response_detail(response: requests.Response) -> str:
    """Extract an API error's detail field, falling back to response text."""
    try:
        body = response.json()
    except requests.exceptions.JSONDecodeError:
        body = None
    if isinstance(body, dict) and "detail" in body:
        detail = body["detail"]
        return detail if isinstance(detail, str) else str(detail)
    return response.text or f"API request failed with status {response.status_code}"
