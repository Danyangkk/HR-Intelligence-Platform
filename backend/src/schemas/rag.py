from typing import Any

from pydantic import BaseModel, Field


class DocumentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    l3_id: str
    top_k: int = Field(5, ge=1, le=20)
    meta_filters: dict[str, Any] | None = None
    only_current: bool = True
