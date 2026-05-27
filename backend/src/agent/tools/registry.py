"""Unified tool layer — agents call tools only, not raw services."""

from __future__ import annotations

from typing import Any, Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Category, FeishuSync, Template
from src.services.agent.structured_query import query_structured as _query_structured
from src.services.metrics.calc import calculate_metric, calculate_operation
from src.services.metrics.dictionary import list_categories as _list_metric_categories
from src.services.rag_search import search_documents as _search_documents
from src.services.rbac import pii_check as _pii_check
from src.services.source import source_of

ToolFn = Callable[..., Awaitable[Any] | Any]

TOOL_NAMES = (
    "list_categories",
    "get_template",
    "query_structured",
    "search_documents",
    "feishu_status",
    "pii_check",
    "calc",
    "chart_render",
)


async def tool_list_categories(db: AsyncSession) -> dict[str, Any]:
    from sqlalchemy import select

    result = await db.execute(select(Category).order_by(Category.sort, Category.id))
    rows = result.scalars().all()
    l3 = [
        {
            "id": cat.id,
            "name": cat.name,
            "source": cat.source or source_of(cat.id),
        }
        for cat in rows
        if cat.level == 3
    ]
    return {"categories": l3, "metric_categories": _list_metric_categories()}


async def tool_get_template(db: AsyncSession, *, l3_id: str) -> dict[str, Any]:
    cat = await db.get(Category, l3_id)
    tpl = await db.get(Template, l3_id)
    if not cat or not tpl:
        raise ValueError(f"未知数据表：{l3_id}")
    return {
        "l3_id": l3_id,
        "name": cat.name,
        "source": cat.source or source_of(l3_id),
        "columns": tpl.columns,
        "filters": tpl.filters,
        "unique_key": tpl.unique_key,
    }


async def tool_query_structured(
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
    return await _query_structured(
        db,
        l3_id=l3_id,
        filters=filters,
        search=search,
        page=page,
        page_size=page_size,
        role=role,
        group_by=group_by,
        aggregations=aggregations,
        limit=limit,
    )


async def tool_search_documents(
    db: AsyncSession,
    *,
    l3_id: str,
    query: str,
    top_k: int = 5,
    meta_filters: dict[str, Any] | None = None,
    only_current: bool = True,
) -> dict[str, Any]:
    return await _search_documents(
        db,
        l3_id=l3_id,
        query=query,
        top_k=top_k,
        meta_filters=meta_filters,
        only_current=only_current,
    )


async def tool_feishu_status(db: AsyncSession, *, l3_id: str) -> dict[str, Any]:
    cat = await db.get(Category, l3_id)
    src = (cat.source if cat else None) or source_of(l3_id)
    if src != "feishu":
        return {"l3_id": l3_id, "status": "not_feishu", "last_sync_at": None}
    sync = await db.get(FeishuSync, l3_id)
    if not sync:
        return {"l3_id": l3_id, "status": "idle", "last_sync_at": None}
    return {
        "l3_id": l3_id,
        "status": sync.status,
        "last_sync_at": sync.last_sync_at.isoformat() if sync.last_sync_at else None,
        "error_msg": sync.error_msg,
    }


def tool_pii_check(role: str, l3_id: str, fields: list[str]) -> dict[str, Any]:
    access = _pii_check(role, l3_id, fields)
    return {"l3_id": l3_id, "role": role, "field_access": access}


def tool_calc(
    *,
    metric: str | None = None,
    operation: str | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = inputs or {}
    if metric:
        return calculate_metric(metric, payload).to_dict()
    if operation:
        return calculate_operation(operation, payload).to_dict()
    raise ValueError("calc 需要 metric 或 operation")


def tool_chart_render(spec: dict[str, Any]) -> dict[str, Any]:
    chart_type = spec.get("type") or "bar"
    data = spec.get("data") or []
    if not data:
        raise ValueError("chart_render 需要非空 data")
    return {
        "type": chart_type,
        "title": spec.get("title") or "",
        "x_field": spec.get("x_field") or "name",
        "y_field": spec.get("y_field") or "value",
        "data": data,
        "rendered": True,
    }


TOOLS: dict[str, ToolFn] = {
    "list_categories": tool_list_categories,
    "get_template": tool_get_template,
    "query_structured": tool_query_structured,
    "search_documents": tool_search_documents,
    "feishu_status": tool_feishu_status,
    "pii_check": tool_pii_check,
    "calc": tool_calc,
    "chart_render": tool_chart_render,
}


async def invoke_tool(name: str, db: AsyncSession | None = None, **kwargs: Any) -> Any:
    fn = TOOLS.get(name)
    if not fn:
        raise ValueError(f"未知 tool：{name}")
    if name in {"pii_check", "calc", "chart_render"}:
        return fn(**kwargs)  # type: ignore[misc]
    if db is None:
        raise ValueError(f"tool {name} 需要 db 会话")
    return await fn(db, **kwargs)


def call_tool(name: str, **kwargs: Any) -> Any:
    """Invoke stateless sync tools (calc, chart_render, pii_check) from sync agent nodes."""
    if name not in {"pii_check", "calc", "chart_render"}:
        raise ValueError(f"call_tool 仅支持同步 tool，收到：{name}")
    fn = TOOLS[name]
    return fn(**kwargs)  # type: ignore[misc]
