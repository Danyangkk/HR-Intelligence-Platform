from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.response import ok
from src.db.session import get_db
from src.models import Category, FeishuSync, Template
from src.services.source import source_of

router = APIRouter(prefix="/categories", tags=["categories"])


def _node(cat: Category, children: list[dict] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"id": cat.id, "name": cat.name, "level": cat.level}
    if cat.level == 3:
        item["source"] = cat.source or source_of(cat.id)
    if children is not None:
        item["children"] = children
    return item


@router.get("")
async def list_categories(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    result = await db.execute(select(Category).order_by(Category.sort, Category.id))
    rows = result.scalars().all()
    by_parent: dict[str | None, list[Category]] = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)

    def build(parent_id: str | None) -> list[dict]:
        items: list[dict] = []
        for cat in by_parent.get(parent_id, []):
            if cat.level == 3:
                items.append(_node(cat))
            else:
                items.append(_node(cat, build(cat.id)))
        return items

    return ok(build(None))


@router.get("/{l3_id}/template")
async def get_template(l3_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    cat = await db.get(Category, l3_id)
    if not cat or cat.level != 3:
        return ok(None, msg="not found")
    tpl = await db.get(Template, l3_id)
    if not tpl:
        return ok({"columns": [], "filters": [], "unique_key": []})
    return ok(
        {
            "l3_id": l3_id,
            "name": cat.name,
            "source": cat.source or source_of(l3_id),
            "columns": tpl.columns,
            "filters": tpl.filters,
            "unique_key": tpl.unique_key,
        }
    )
