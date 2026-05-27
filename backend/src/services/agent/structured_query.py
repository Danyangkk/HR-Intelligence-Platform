from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Category, Template
from src.services.agent.aggregation import query_aggregated
from src.services.records import query_records, record_to_item
from src.services.rbac import mask_items
from src.services.source import source_of


async def query_structured(
    db: AsyncSession,
    *,
    l3_id: str,
    filters: dict[str, str] | None = None,
    search: str = "",
    page: int = 1,
    page_size: int = 20,
    role: str = "viewer",
    group_by: list[str] | None = None,
    aggregations: list[dict[str, str]] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    tpl = await db.get(Template, l3_id)
    if not tpl:
        raise ValueError(f"未知数据表：{l3_id}")

    cat = await db.get(Category, l3_id)
    module = cat.name if cat else l3_id

    if aggregations:
        agg_result = await query_aggregated(
            db,
            l3_id,
            tpl,
            filters=filters or {},
            search=search.strip(),
            group_by=group_by,
            aggregations=aggregations,
            limit=limit,
        )
        return {
            "l3_id": l3_id,
            "module": module,
            "items": [],
            "agg": agg_result.get("agg"),
            "grouped_rows": agg_result.get("rows"),
            "group_by": agg_result.get("group_by"),
            "mode": agg_result.get("mode"),
            "total": len(agg_result.get("rows") or []) or (1 if agg_result.get("agg") else 0),
        }

    records, total = await query_records(
        db,
        l3_id,
        tpl,
        page=page,
        page_size=page_size,
        search=search.strip(),
        filters=filters or {},
    )
    items = [record_to_item(record, tpl) for record in records]
    items = mask_items(role, l3_id, items)
    source = (cat.source if cat else None) or source_of(l3_id)
    return {
        "l3_id": l3_id,
        "module": module,
        "source": source,
        "items": items,
        "total": total,
        "pagination": {"page": page, "page_size": page_size, "total": total},
        "mode": "rows",
    }
