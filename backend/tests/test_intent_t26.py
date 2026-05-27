from __future__ import annotations

import pytest

from src.agent.graph import run_agent
from src.agent.planner_rules import build_plan, classify_intent, extract_list_filters, filter_roster_rows
from src.db.session import AsyncSessionLocal


def test_classify_list_intent():
    assert classify_intent("运营组 P5 以上员工名单") == "list"


def test_classify_aggregate_intent():
    assert classify_intent("各事业部 11 月请假总天数") == "aggregate"


def test_classify_trend_intent():
    assert classify_intent("杭抖部门近几个月离职率走势") == "trend"


def test_classify_forecast_intent():
    assert classify_intent("下季度编制缺口预测") == "forecast"


def test_build_plan_list_has_roster_target():
    plan = build_plan("list", "运营组 P5 以上员工名单")
    retrieve = next(item for item in plan if item["type"] == "retrieve")
    assert retrieve["target_l3"] == ["l3-2-1-4"]


def test_build_plan_aggregate_has_group_by():
    plan = build_plan("aggregate", "各事业部请假总天数")
    retrieve = next(item for item in plan if item["type"] == "retrieve")
    assert retrieve.get("group_by")
    assert retrieve.get("aggregations")


def test_filter_roster_p5_plus():
    rows = [
        {"姓名": "张三", "工号": "A0123", "序列": "P5"},
        {"姓名": "周琪", "工号": "A0301", "序列": "P5"},
    ]
    filtered = filter_roster_rows(rows, extract_list_filters("P5 以上"))
    assert len(filtered) == 2


@pytest.mark.asyncio
async def test_agent_list_roster():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="运营组 P5 以上员工名单", role="viewer")
    assert result["intent"] == "list"
    assert result.get("answer")
    assert "运营" in result["answer"] or "A0" in result["answer"]


@pytest.mark.asyncio
async def test_agent_trend_turnover():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="杭抖部门离职率走势", role="viewer")
    assert result["intent"] == "trend"
    assert result.get("answer")
