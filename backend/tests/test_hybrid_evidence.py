"""Hybrid evidence path tests (PR3)."""

from __future__ import annotations

from src.agent.critic import _evidence_gaps_for_plan, run_critic_rules
from src.agent.planner_llm import validate_plan_invariants


def _hybrid_plan() -> list[dict]:
    return [
        {"id": "t1", "type": "resolve", "goal": "解析", "assigned_agent": "Resolver"},
        {
            "id": "t2",
            "type": "retrieve",
            "goal": "结构化离职数据",
            "target_l3": ["l3-2-5-1"],
            "retrieve_mode": "structured",
            "assigned_agent": "Retriever",
        },
        {
            "id": "t3",
            "type": "retrieve",
            "goal": "制度文档",
            "target_l3": ["l3-1-3-3"],
            "retrieve_mode": "rag",
            "assigned_agent": "Retriever",
        },
        {"id": "t4", "type": "analyze", "goal": "归因", "assigned_agent": "Analyst"},
        {"id": "t5", "type": "critique", "goal": "质检", "assigned_agent": "Critic"},
        {"id": "t6", "type": "compose", "goal": "汇总", "assigned_agent": "Composer"},
    ]


def test_hybrid_plan_passes_invariants():
    assert validate_plan_invariants(_hybrid_plan()) is True


def test_critic_detects_missing_rag_evidence():
    plan = _hybrid_plan()
    state = {
        "intent": "attribution",
        "plan": plan,
        "replan_count": 0,
        "analysis": {"sufficient": True, "factors": [{"name": "考核", "contribution": 0.3}]},
        "evidence": [{"kind": "structured", "l3_id": "l3-2-5-1", "rows": [{"事业部": "杭抖部门"}]}],
    }
    gaps = _evidence_gaps_for_plan(state, plan)
    assert "missing: rag l3-1-3-3" in gaps

    result = run_critic_rules(state)
    assert result["needs_replan"] is True
    assert "missing: rag l3-1-3-3" in (result.get("replan_gaps") or [])


def test_critic_passes_with_mixed_evidence():
    plan = _hybrid_plan()
    state = {
        "intent": "attribution",
        "plan": plan,
        "replan_count": 0,
        "analysis": {"sufficient": True, "factors": [{"name": "考核", "contribution": 0.3}]},
        "evidence": [
            {"kind": "structured", "l3_id": "l3-2-5-1", "rows": [{"事业部": "杭抖部门"}]},
            {"kind": "documents", "l3_id": "l3-1-3-3", "hits": [{"text": "考核规则片段", "score": 0.9}]},
        ],
    }
    result = run_critic_rules(state)
    assert result["needs_replan"] is False


def test_lookup_without_analyze_skips_replan():
    plan = [
        {"id": "t1", "type": "resolve", "goal": "解析", "assigned_agent": "Resolver"},
        {
            "id": "t2",
            "type": "retrieve",
            "goal": "请假",
            "target_l3": ["l3-2-2-1"],
            "retrieve_mode": "structured",
            "assigned_agent": "Retriever",
        },
        {"id": "t3", "type": "compose", "goal": "汇总", "assigned_agent": "Composer"},
    ]
    state = {
        "intent": "lookup",
        "plan": plan,
        "replan_count": 0,
        "evidence": [],
    }
    result = run_critic_rules(state)
    assert result["needs_replan"] is False
