from __future__ import annotations

import pytest

from src.agent.analyst_rules import run_analyst_rules
from src.agent.graph import run_agent
from src.agent.metric_resolver import resolve_metric_from_text
from src.db.session import AsyncSessionLocal


def _state(*, intent: str, question: str, entities: dict, evidence: list) -> dict:
    return {
        "intent": intent,
        "question": question,
        "entities": entities,
        "evidence": evidence,
        "trace": [],
    }


def test_analyst_attribution_uses_resolver_metric_spec():
    metric = resolve_metric_from_text("张三为什么绩效很差", "绩效很差")
    assert metric is not None
    state = _state(
        intent="attribution",
        question="张三为什么绩效很差",
        entities={"topic": "绩效", "employee": {"工号": "A0123", "姓名": "张三"}, "metric": metric},
        evidence=[
            {
                "kind": "structured",
                "l3_id": "l3-5-1-1",
                "rows": [
                    {"工号": "A0123", "姓名": "张三", "部门": "运营组", "考核周期": "2025H2", "绩效得分": 65, "绩效等级": "C", "部门排名": 18},
                    {"工号": "A0188", "姓名": "王五", "部门": "运营组", "考核周期": "2025H2", "绩效得分": 72, "绩效等级": "B", "部门排名": 12},
                ],
            }
        ],
    )
    result = run_analyst_rules(state)
    analysis = result.get("analysis") or {}
    assert analysis.get("metric", {}).get("name") == "绩效分布偏离"
    assert analysis.get("citation") == metric["citation"]
    assert any("绩效分布偏离" in f for f in analysis.get("factors") or [])


def test_analyst_compare_uses_resolver_metric_spec():
    metric = resolve_metric_from_text("对比各事业部人均成本谁高", "成本高")
    assert metric is not None
    state = _state(
        intent="compare",
        question="对比各事业部人均成本谁高",
        entities={"metric": metric},
        evidence=[
            {
                "kind": "structured",
                "l3_id": "l3-4-6-3",
                "rows": [
                    {"事业部": "杭抖部门", "人均成本": 1.2, "人数": 10},
                    {"事业部": "杭综部门", "人均成本": 0.9, "人数": 8},
                ],
            }
        ],
    )
    result = run_analyst_rules(state)
    analysis = result.get("analysis") or {}
    assert analysis.get("metric", {}).get("name") == "人均人力成本"
    assert analysis.get("citation") == metric["citation"]


@pytest.mark.asyncio
async def test_e2e_attribution_analysis_carries_metric():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="张三为什么绩效很差", role="viewer")
    if result.get("clarify"):
        pytest.skip("resolver returned clarify")
    analysis = result.get("analysis") or {}
    metric = (result.get("entities") or {}).get("metric") or {}
    assert metric.get("name") == "绩效分布偏离"
    assert (analysis.get("metric") or {}).get("name") == "绩效分布偏离"
