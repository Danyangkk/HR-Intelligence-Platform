from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ImportValidateRequest(BaseModel):
    headers: list[str]


class ImportPreviewRequest(BaseModel):
    headers: list[str]
    rows: list[list[Any]]


class ImportCommitRequest(BaseModel):
    headers: list[str]
    rows: list[list[Any]]
    dup_strategy: Literal["skip", "overwrite", "add"] = "skip"


class RecordUpdateRequest(BaseModel):
    fields: dict[str, Any]


class RecordDeleteRequest(BaseModel):
    ids: list[int]
