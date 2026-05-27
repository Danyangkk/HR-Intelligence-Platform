from __future__ import annotations

import io
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.response import ok
from src.db.session import get_db
from src.models import Category, DataRecord, Template
from src.api.deps import CurrentUser, get_optional_user, require_write, resolve_role
from src.services.audit import write_audit
from src.services.rbac import can_read_l3, mask_items
from src.schemas.importing import (
    ImportCommitRequest,
    ImportPreviewRequest,
    ImportValidateRequest,
    RecordDeleteRequest,
    RecordUpdateRequest,
)
from src.services.import_service import (
    commit_rows,
    load_existing_hashes,
    preview_rows,
    validate_headers,
)
from src.services.records import (
    build_filter_options,
    build_filtered_query,
    compute_uk_hash,
    query_records,
    record_to_item,
)
from src.services.source import source_of

router = APIRouter(prefix="/data", tags=["data"])


def _parse_filters(request: Request) -> dict[str, str]:
    filters: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if key.startswith("filters[") and key.endswith("]") and value:
            field = key[len("filters[") : -1]
            filters[field] = value
    return filters


async def _load_data_table(db: AsyncSession, l3_id: str) -> tuple[Category, Template]:
    cat = await db.get(Category, l3_id)
    if not cat or cat.level != 3:
        raise HTTPException(status_code=404, detail="category not found")
    src = cat.source or source_of(l3_id)
    if src not in {"feishu", "import"}:
        raise HTTPException(status_code=400, detail="not a structured data table")
    tpl = await db.get(Template, l3_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="template not found")
    return cat, tpl


async def _load_import_table(db: AsyncSession, l3_id: str) -> tuple[Category, Template]:
    cat, tpl = await _load_data_table(db, l3_id)
    src = cat.source or source_of(l3_id)
    if src != "import":
        raise HTTPException(status_code=403, detail="table is read-only")
    return cat, tpl


@router.get("/{l3_id}")
async def list_data(
    l3_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    role = resolve_role(user)
    if not can_read_l3(role, l3_id):
        raise HTTPException(status_code=403, detail="无权访问该数据表")
    cat, tpl = await _load_data_table(db, l3_id)
    src = cat.source or source_of(l3_id)
    filters = _parse_filters(request)
    records, total = await query_records(
        db,
        l3_id,
        tpl,
        page=page,
        page_size=page_size,
        search=search.strip(),
        filters=filters,
    )
    items = mask_items(role, l3_id, [record_to_item(record, tpl) for record in records])
    return ok(
        {
            "l3_id": l3_id,
            "source": src,
            "readonly": src == "feishu",
            "columns": tpl.columns,
            "items": items,
            "pagination": {"page": page, "page_size": page_size, "total": total},
        }
    )


@router.get("/{l3_id}/filters")
async def list_filters(l3_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    _, tpl = await _load_data_table(db, l3_id)
    options = await build_filter_options(db, l3_id, tpl)
    return ok({"l3_id": l3_id, "filters": options})


@router.get("/{l3_id}/export")
async def export_data(
    l3_id: str,
    request: Request,
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    cat, tpl = await _load_data_table(db, l3_id)
    filters = _parse_filters(request)
    query = build_filtered_query(l3_id, tpl, search=search.strip(), filters=filters)
    result = await db.execute(query.order_by(DataRecord.id.desc()))
    records = result.scalars().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append(list(tpl.columns))
    for record in records:
        payload = record.payload or {}
        ws.append([payload.get(col, "") for col in tpl.columns])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"{cat.name}-导出.xlsx"
    encoded_name = quote(filename)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="export.xlsx"; filename*=UTF-8\'\'{encoded_name}'
        )
    }
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.post("/{l3_id}/import/validate")
async def import_validate(
    l3_id: str,
    body: ImportValidateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _, tpl = await _load_import_table(db, l3_id)
    result = validate_headers(tpl, body.headers)
    return ok({"l3_id": l3_id, **result})


@router.post("/{l3_id}/import/preview")
async def import_preview(
    l3_id: str,
    body: ImportPreviewRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _, tpl = await _load_import_table(db, l3_id)
    header_check = validate_headers(tpl, body.headers)
    if not header_check["ok"]:
        raise HTTPException(status_code=400, detail="header validation failed", headers={"X-Header-Ok": "0"})
    existing_hashes = await load_existing_hashes(db, l3_id)
    preview = preview_rows(tpl, body.headers, body.rows, existing_hashes)
    return ok({"l3_id": l3_id, **preview})


@router.post("/{l3_id}/import/commit")
async def import_commit(
    l3_id: str,
    body: ImportCommitRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    require_write(user)
    _, tpl = await _load_import_table(db, l3_id)
    header_check = validate_headers(tpl, body.headers)
    if not header_check["ok"]:
        raise HTTPException(status_code=400, detail="header validation failed")
    try:
        result = await commit_rows(db, l3_id, tpl, body.headers, body.rows, body.dup_strategy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await write_audit(
        db,
        actor=None if user.username == "anonymous" else user.username,
        action="data.import.commit",
        l3_id=l3_id,
        detail={"committed": result.get("committed"), "skipped": result.get("skipped")},
    )
    return ok({"l3_id": l3_id, **result})


@router.put("/{l3_id}/{record_id}")
async def update_record(
    l3_id: str,
    record_id: int,
    body: RecordUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    require_write(user)
    _, tpl = await _load_import_table(db, l3_id)
    record = await db.get(DataRecord, record_id)
    if not record or record.l3_id != l3_id:
        raise HTTPException(status_code=404, detail="record not found")

    payload = dict(record.payload or {})
    for col in tpl.columns:
        if col in body.fields:
            payload[col] = body.fields[col]

    req_cols = _required_columns_from_tpl(tpl)
    for col in req_cols:
        if str(payload.get(col, "") or "").strip() == "":
            raise HTTPException(status_code=400, detail=f"{col}不能为空")

    if "事业部" in tpl.columns:
        bu = str(payload.get("事业部", "") or "").strip()
        if bu and bu not in {"杭综部门", "杭抖部门", "职能部门"}:
            raise HTTPException(status_code=400, detail="事业部非法值")

    uk_hash = compute_uk_hash(tpl.unique_key, payload)
    dup = await db.scalar(
        select(DataRecord.id).where(
            DataRecord.l3_id == l3_id,
            DataRecord.uk_hash == uk_hash,
            DataRecord.id != record_id,
        )
    )
    if dup:
        raise HTTPException(status_code=409, detail="unique key conflict")

    record.payload = payload
    record.uk_hash = uk_hash
    await db.commit()
    await db.refresh(record)
    await write_audit(
        db,
        actor=None if user.username == "anonymous" else user.username,
        action="data.record.update",
        l3_id=l3_id,
        target_id=str(record_id),
    )
    return ok(record_to_item(record, tpl))


def _required_columns_from_tpl(tpl: Template) -> list[str]:
    cols = list(tpl.columns)
    keys = list(tpl.unique_key or [])
    return list(dict.fromkeys([cols[0], *keys])) if cols else keys


@router.delete("/{l3_id}")
async def delete_records(
    l3_id: str,
    body: RecordDeleteRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    require_write(user)
    await _load_import_table(db, l3_id)
    if not body.ids:
        return ok({"deleted": 0})

    result = await db.execute(
        select(DataRecord).where(DataRecord.l3_id == l3_id, DataRecord.id.in_(body.ids))
    )
    records = list(result.scalars().all())
    for record in records:
        await db.delete(record)
    await db.commit()
    await write_audit(
        db,
        actor=None if user.username == "anonymous" else user.username,
        action="data.record.delete",
        l3_id=l3_id,
        detail={"deleted": len(records), "ids": [r.id for r in records]},
    )
    return ok({"deleted": len(records), "ids": [r.id for r in records]})
