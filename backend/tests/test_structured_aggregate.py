from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.db.session import AsyncSessionLocal
from src.models import DataRecord, Template
from src.services.agent.aggregation import query_aggregated


@pytest.mark.asyncio
async def test_query_aggregated_sum():
    async with AsyncSessionLocal() as db:
        tpl = await db.get(Template, "l3-2-2-4")
        assert tpl is not None
        count = await db.scalar(
            select(func.count()).select_from(DataRecord).where(DataRecord.l3_id == "l3-2-2-4")
        )
        if count is None:
            pytest.skip("无加班明细种子数据")

        result = await query_aggregated(
            db,
            "l3-2-2-4",
            tpl,
            filters={},
            search="",
            group_by=None,
            aggregations=[{"field": "加班时长", "op": "sum"}],
            limit=10,
        )
    assert result["mode"] == "aggregate"
    assert "agg" in result
    assert any(k.endswith("_sum") for k in result["agg"])
