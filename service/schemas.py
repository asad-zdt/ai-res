"""Pydantic request and response schemas for the resource prediction API."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_APP_NAME_PATTERN = re.compile(r"^[a-z0-9_.-]{1,64}$")


class ResourceMetrics(BaseModel):
    """Non-negative resource usage metrics."""

    cpu_pct: float = Field(ge=0)
    ram_mb: float = Field(ge=0)
    disk_mbps: float = Field(ge=0)
    net_kbps: float = Field(ge=0)


class PredictRequest(BaseModel):
    """Application identifier submitted for prediction or execution."""

    app_name: str

    @field_validator("app_name")
    @classmethod
    def normalize_app_name(cls, value: str) -> str:
        """Normalize and validate a safe application identifier."""
        normalized = value.strip().lower()
        if not _APP_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("app_name must match ^[a-z0-9_.-]{1,64}$")
        return normalized


class PredictResponse(BaseModel):
    """Resource prediction response."""

    app_name: str
    predicted: ResourceMetrics
    source: Literal["model", "mock"]


class EnforcementInfo(BaseModel):
    """Admission-control and operating-system enforcement outcome."""

    admitted: bool
    reason: str | None
    niceness: int | None
    cgroup_applied: bool


class RunAndCompareResponse(BaseModel):
    """Prediction, observed resource usage, and enforcement outcome."""

    app_name: str
    predicted: ResourceMetrics
    actual: ResourceMetrics
    duration_s: float = Field(ge=0)
    enforcement: EnforcementInfo
