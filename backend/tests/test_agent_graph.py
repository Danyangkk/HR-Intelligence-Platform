from __future__ import annotations

import pytest

from src.agent.graph import run_agent
from src.db.session import AsyncSessionLocal


@pytest.mark.asyncio
async def test_agent_lookup_leave_question():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="张三11月请了几天假", role="viewer")
    assert result["intent"] == "lookup"
    assert result["rejected"] is False
    assert result["answer"]
    assert isinstance(result["trace"], list)
    assert any(item.get("agent") == "Planner" for item in result["trace"])


@pytest.mark.asyncio
async def test_agent_rejects_personal_salary():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="张三的工资条是多少", role="viewer")
    assert result["rejected"] is True
    assert "薪资" in result["answer"]
