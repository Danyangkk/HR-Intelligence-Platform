from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AggregationSpec(BaseModel):
    field: str
    op: str


class StructuredQueryRequest(BaseModel):
    l3_id: str
    filters: dict[str, str] = Field(default_factory=dict)
    search: str = ""
    page: int = 1
    page_size: int = 20
    group_by: list[str] = Field(default_factory=list)
    aggregations: list[AggregationSpec] = Field(default_factory=list)
    limit: int = Field(100, ge=1, le=500)


class AgentAskRequest(BaseModel):
    question: str
    role: str = "viewer"
    history: list[dict[str, Any]] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    stream: bool = False
