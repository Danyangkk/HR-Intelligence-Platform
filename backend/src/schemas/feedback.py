from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentFeedbackRequest(BaseModel):
    run_id: str
    rating: Literal["up", "down"]
    reason: Literal["wrong", "irrelevant", "bad_data", "over_reject", "other"] | None = None
    note: str | None = Field(default=None, max_length=500)


class BadcaseReviewUpdate(BaseModel):
    review_status: Literal["pending", "reviewed", "fixed", "ignored"]
