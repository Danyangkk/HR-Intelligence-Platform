from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import APPROVAL_STATUSES, BU_UNITS
from src.models import DataRecord, Template

MONTH_FILTER_RE = re.compile(r"^\d{4}-\d{2}$")


def compute_uk_hash(unique_key: list[str], payload: dict[str, Any]) -> str:
    parts = [str(payload.get(key, "") or "").strip() for key in unique_key]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def build_locator(unique_key: list[str], payload: dict[str, Any]) -> list[dict[str, str]]:
    return [{"field": key, "value": str(payload.get(key, "") or "")} for key in unique_key]


def record_to_item(record: DataRecord, template: Template) -> dict[str, Any]:
    payload = dict(record.payload or {})
    item = {"id": record.id, **payload}
    item["_locator"] = build_locator(template.unique_key, payload)
    return item


def apply_filters(query: Select, template: Template, filters: dict[str, Any]) -> Select:
    for field, value in filters.items():
        if not value:
            continue
        col = DataRecord.payload[field].astext
        if isinstance(value, dict):
            start = value.get("from") or value.get("start")
            end = value.get("to") or value.get("end")
            if start and end:
                query = query.where(col >= str(start), col <= str(end))
            elif start:
                query = query.where(col.like(f"{str(start)[:7]}%"))
            continue
        text = str(value)
        if MONTH_FILTER_RE.match(text):
            query = query.where(col.like(f"{text}%"))
        else:
            query = query.where(col == text)
    return query


def apply_search(query: Select, template: Template, search: str) -> Select:
    if not search:
        return query
    keyword = f"%{search.strip()}%"
    clauses = [DataRecord.payload[col].astext.ilike(keyword) for col in template.columns]
    if clauses:
        query = query.where(or_(*clauses))
    return query


async def query_records(
    db: AsyncSession,
    l3_id: str,
    template: Template,
    *,
    page: int,
    page_size: int,
    search: str,
    filters: dict[str, str],
) -> tuple[list[DataRecord], int]:
    query = select(DataRecord).where(DataRecord.l3_id == l3_id)
    query = apply_filters(query, template, filters)
    query = apply_search(query, template, search)

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = max(page - 1, 0) * page_size
    result = await db.execute(query.order_by(DataRecord.id.desc()).offset(offset).limit(page_size))
    return list(result.scalars().all()), int(total)


def build_filtered_query(
    l3_id: str,
    template: Template,
    *,
    search: str,
    filters: dict[str, str],
) -> Select:
    query = select(DataRecord).where(DataRecord.l3_id == l3_id)
    query = apply_filters(query, template, filters)
    query = apply_search(query, template, search)
    return query


async def build_filter_options(db: AsyncSession, l3_id: str, template: Template) -> dict[str, list[str]]:
    options: dict[str, list[str]] = {}
    for spec in template.filters or []:
        field = spec.get("field")
        ftype = spec.get("type")
        if not field:
            continue
        if ftype == "bu":
            options[field] = BU_UNITS.copy()
            continue
        if ftype == "approval_status":
            options[field] = APPROVAL_STATUSES.copy()
            continue
        col = DataRecord.payload[field].astext
        result = await db.execute(
            select(col).where(DataRecord.l3_id == l3_id, col.is_not(None), col != "").distinct()
        )
        values = sorted({row[0] for row in result.all() if row[0]})
        if ftype == "month":
            months: set[str] = set()
            for value in values:
                match = re.match(r"^(\d{4}-\d{2})", str(value))
                if match:
                    months.add(match.group(1))
            options[field] = sorted(months, reverse=True)
        else:
            options[field] = values
    return options
