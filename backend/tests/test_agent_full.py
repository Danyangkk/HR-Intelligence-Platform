from __future__ import annotations

import pytest

from src.agent.graph import run_agent
from src.db.session import AsyncSessionLocal


@pytest.mark.asyncio
async def test_agent_compare_bu_cost():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="对比各事业部人均成本谁高", role="viewer")
    assert result["intent"] == "compare"
    assert result["rejected"] is False
    assert "杭抖" in result["answer"] or "事业部" in result["answer"]
    assert result.get("charts")
    assert any(item.get("agent") == "Analyst" for item in result["trace"])


@pytest.mark.asyncio
async def test_agent_attribution_turnover():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="为什么运营组离职率偏高", role="viewer")
    assert result["intent"] == "attribution"
    assert result["rejected"] is False
    assert result["answer"]
    assert any(item.get("agent") == "Critic" for item in result["trace"])


@pytest.mark.asyncio
async def test_agent_attribution_performance():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="张三绩效为什么较差", role="viewer")
    assert result["intent"] == "attribution"
    assert "张三" in result["answer"] or "绩效" in result["answer"]
