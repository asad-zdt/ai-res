"""Tests for API request and response schemas."""

import pytest
from pydantic import ValidationError

from service.schemas import (
    EnforcementInfo,
    PredictRequest,
    ResourceMetrics,
    RunAndCompareResponse,
)


def test_valid_request() -> None:
    """Accept a valid application identifier."""
    assert PredictRequest(app_name="chrome").app_name == "chrome"


def test_request_normalizes_uppercase() -> None:
    """Strip whitespace and lowercase the application identifier."""
    assert PredictRequest(app_name="  Chrome  ").app_name == "chrome"


def test_request_accepts_maximum_identifier_length() -> None:
    """Accept identifiers at the configured 64-character boundary."""
    assert PredictRequest(app_name="a" * 64).app_name == "a" * 64


@pytest.mark.parametrize("app_name", ["", "../etc/passwd"])
def test_request_rejects_invalid_app_name(app_name: str) -> None:
    """Reject empty identifiers and path-like values."""
    with pytest.raises(ValidationError):
        PredictRequest(app_name=app_name)


@pytest.mark.parametrize("app_name", ["a" * 65, "name with spaces", "café"])
def test_request_rejects_invalid_identifier_boundaries(app_name: str) -> None:
    """Reject identifiers that exceed the limit or contain unsafe characters."""
    with pytest.raises(ValidationError):
        PredictRequest(app_name=app_name)


def test_resource_metrics_reject_negative_value() -> None:
    """Reject negative resource metrics."""
    with pytest.raises(ValidationError):
        ResourceMetrics(cpu_pct=-0.1, ram_mb=0, disk_mbps=0, net_kbps=0)


def test_resource_metrics_accept_zero_and_reject_nan() -> None:
    """Accept zero-valued metrics and reject non-finite NaN input."""
    metrics = ResourceMetrics(cpu_pct=0, ram_mb=0, disk_mbps=0, net_kbps=0)
    assert metrics.cpu_pct == 0

    with pytest.raises(ValidationError):
        ResourceMetrics(cpu_pct=float("nan"), ram_mb=0, disk_mbps=0, net_kbps=0)


def test_run_and_compare_response_round_trip() -> None:
    """Serialize and validate a complete run-and-compare response."""
    response = RunAndCompareResponse(
        app_name="chrome",
        predicted=ResourceMetrics(
            cpu_pct=35.2, ram_mb=820.5, disk_mbps=1.4, net_kbps=210.0
        ),
        actual=ResourceMetrics(
            cpu_pct=32.8, ram_mb=790.0, disk_mbps=1.2, net_kbps=205.0
        ),
        duration_s=12.5,
        enforcement=EnforcementInfo(
            admitted=True,
            reason=None,
            niceness=0,
            cgroup_applied=True,
        ),
    )

    restored = RunAndCompareResponse.model_validate(response.model_dump())

    assert restored == response
