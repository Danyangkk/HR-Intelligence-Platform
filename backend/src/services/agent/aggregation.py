from __future__ import annotations

from typing import Any

from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import DataRecord, Template
from src.services.records import apply_filters, apply_search

_AGG_OPS = frozenset({"sum", "avg", "count", "max", "min"})


def _agg_expr(field: str, op: str):
    if op == "count":
        return func.count(DataRecord.id).label(f"{field}_count")
    col = cast(DataRecord.payload[field].astext, Numeric)
    if op == "sum":
        return func.sum(col).label(f"{field}_sum")
    if op == "avg":
        return func.avg(col).label(f"{field}_avg")
    if op == "max":
        return func.max(col).label(f"{field}_max")
    if op == "min":
        return func.min(col).label(f"{field}_min")
    raise ValueError(f"不支持的聚合 op：{op}")


async def query_aggregated(
    db: AsyncSession,
    l3_id: str,
    template: Template,
    *,
    filters: dict[str, str],
    search: str,
    group_by: list[str] | None,
    aggregations: list[dict[str, str]],
    limit: int = 100,
) -> dict[str, Any]:
    if not aggregations:
        raise ValueError("aggregations 不能为空")

    columns = template.columns or []
    for agg in aggregations:
        op = str(agg.get("op") or "").lower()
        field = str(agg.get("field") or "")
        if op not in _AGG_OPS:
            raise ValueError(f"不支持的聚合 op：{op}")
        if op != "count" and field not in columns:
            raise ValueError(f"字段不在模版中：{field}")

    group_by = list(group_by or [])
    for field in group_by:
        if field not in columns:
            raise ValueError(f"group_by 字段不在模版中：{field}")

    select_cols: list[Any] = []
    group_cols = []
    for field in group_by:
        col = DataRecord.payload[field].astext
        select_cols.append(col.label(field))
        group_cols.append(col)

    for agg in aggregations:
        select_cols.append(_agg_expr(str(agg["field"]), str(agg["op"]).lower()))

    query = select(*select_cols).where(DataRecord.l3_id == l3_id)
    query = apply_filters(query, template, filters)
    query = apply_search(query, template, search)
    if group_cols:
        query = query.group_by(*group_cols)
    query = query.limit(min(max(limit, 1), 500))

    result = await db.execute(query)
    rows: list[dict[str, Any]] = []
    agg_out: dict[str, Any] = {}
    for row in result.mappings().all():
        item = {k: (float(v) if isinstance(v, (int, float)) and v is not None else v) for k, v in dict(row).items()}
        if group_by:
            rows.append(item)
        else:
            agg_out.update(item)

    if group_by:
        return {"mode": "grouped", "group_by": group_by, "rows": rows}
    return {"mode": "aggregate", "agg": agg_out}
