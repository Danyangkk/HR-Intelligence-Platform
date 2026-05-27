from __future__ import annotations

import pytest

from src.agent.graph import run_agent
from src.db.session import AsyncSessionLocal


@pytest.mark.asyncio
async def test_attribution_sets_metric_from_fuzzy_phrase():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="张三为什么绩效很差", role="viewer")
    entities = result.get("entities") or {}
    metric = entities.get("metric") or {}
    assert result.get("intent") == "attribution"
    if not result.get("clarify"):
        assert metric.get("name") == "绩效分布偏离"
        assert metric.get("benchmark")
