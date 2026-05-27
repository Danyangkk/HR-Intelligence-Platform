from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CalcByMetricRequest(BaseModel):
    metric: str
    inputs: dict[str, float | int] = Field(default_factory=dict)


class CalcOperationRequest(BaseModel):
    operation: str
    metric: str | None = None
    numerator: float | None = None
    denominator: float | None = None
    current: float | None = None
    previous: float | None = None


class CalcRequest(BaseModel):
    metric: str | None = None
    inputs: dict[str, float | int] = Field(default_factory=dict)
    operation: str | None = None
    numerator: float | None = None
    denominator: float | None = None
    current: float | None = None
    previous: float | None = None
