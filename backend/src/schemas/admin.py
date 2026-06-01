from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: Literal["tech_super_admin", "biz_super_admin", "staff"]
    display_name: str
    employee_id: str | None = None


class UpdateUserRequest(BaseModel):
    role: Literal["tech_super_admin", "biz_super_admin", "staff"] | None = None
    display_name: str | None = None
    is_active: bool | None = None


class PayrollGrantRequest(BaseModel):
    target_username: str
    reason: str = Field(min_length=1, max_length=500)


class PayrollRevokeRequest(BaseModel):
    target_username: str
    reason: str | None = None


class PayrollConfirmRequest(BaseModel):
    target_ref: str
    entry: str
    fields: str
    reason: str = Field(min_length=1, max_length=500)


class AdoptSuggestionRequest(BaseModel):
    suggestion_id: str
    title: str | None = None
    content: str | None = None
    content_biz: str | None = None
    change_target: str | None = None
    test_requirement: str | None = None
    evidence_run_ids: list[str] = Field(default_factory=list)
    # 来源关联：可选，未传时后端会按 suggestion_id 在 mock report 中反查
    report_id: str | None = None
    finding_id: str | None = None


class RejectSuggestionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class TicketActionRequest(BaseModel):
    note: str | None = None


class TicketNoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
