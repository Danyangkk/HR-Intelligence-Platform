from __future__ import annotations

import pytest

from src.agent.graph import run_agent
from src.agent.planner_rules import (
    build_plan,
    classify_intent,
    is_org_metric_question,
    is_personal_lookup_question,
)
from src.agent.planner_llm import resolve_plan
from src.db.session import AsyncSessionLocal


def test_org_turnover_classified_as_aggregate():
    question = "杭抖事业部的离职率怎么样"
    assert is_org_metric_question(question)
    assert not is_personal_lookup_question(question)
    assert classify_intent(question) == "aggregate"


def test_org_turnover_plan_targets_turnover_table():
    plan = build_plan("aggregate", "杭抖事业部的离职率怎么样")
    retrieve = next(item for item in plan if item["type"] == "retrieve")
    assert retrieve["target_l3"] == ["l3-2-5-1"]


def test_resolve_plan_rejects_org_turnover_lookup(monkeypatch):
    monkeypatch.setattr(
        "src.agent.planner_llm.plan_with_llm",
        lambda *args, **kwargs: {
            "intent": "lookup",
            "reasoning": "误判",
            "plan": [
                {"id": "t1", "type": "resolve", "goal": "x", "assigned_agent": "Resolver"},
                {
                    "id": "t2",
                    "type": "retrieve",
                    "goal": "x",
                    "assigned_agent": "Retriever",
                    "retrieve_mode": "structured",
                    "target_l3": ["l3-5-1-1"],
                },
                {"id": "t3", "type": "compose", "goal": "x", "assigned_agent": "Composer"},
            ],
        },
    )
    out = resolve_plan("杭抖事业部的离职率怎么样")
    assert out["intent"] == "aggregate"
    assert out["source"] == "rules"


@pytest.mark.asyncio
async def test_agent_org_turnover_no_employee_clarify():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="杭抖事业部的离职率怎么样", role="viewer")
    assert result["intent"] == "aggregate"
    answer = result.get("answer") or ""
    assert "哪位员工" not in answer
    assert "运营组" in answer or "7.1" in answer or "7.0" in answer
