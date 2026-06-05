"""Plan invariant validator tests (PR2)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.agent.catalog import valid_l3_ids
from src.agent.planner_llm import validate_plan_invariants
from src.agent.planner_rules import build_plan


def _attribution_plan(*, targets: list[str] | None = None) -> list[dict]:
    return [
        {"id": "t1", "type": "resolve", "goal": "解析", "assigned_agent": "Resolver"},
        {
            "id": "t2",
            "type": "retrieve",
            "goal": "取证",
            "target_l3": targets or ["l3-2-1-4"],
            "retrieve_mode": "structured",
            "assigned_agent": "Retriever",
        },
        {"id": "t3", "type": "analyze", "goal": "分析", "assigned_agent": "Analyst"},
        {"id": "t4", "type": "critique", "goal": "质检", "assigned_agent": "Critic"},
        {"id": "t5", "type": "compose", "goal": "汇总", "assigned_agent": "Composer"},
    ]


def test_i1_valid_plan_passes():
    assert validate_plan_invariants(_attribution_plan()) is True


def test_i1_empty_plan_fails():
    assert validate_plan_invariants([]) is False


def test_i1_invalid_subtask_type_fails():
    plan = _attribution_plan()
    plan[2]["type"] = "summarize"
    assert validate_plan_invariants(plan) is False


def test_i2_compose_must_be_single_and_last_pass():
    plan = [
        {
            "id": "t1",
            "type": "retrieve",
            "goal": "RAG",
            "target_l3": ["l3-1-1-1"],
            "retrieve_mode": "rag",
            "assigned_agent": "Retriever",
        },
        {"id": "t2", "type": "compose", "goal": "汇总", "assigned_agent": "Composer"},
    ]
    assert validate_plan_invariants(plan) is True


def test_i2_missing_compose_fails():
    plan = _attribution_plan()[:-1]
    assert validate_plan_invariants(plan) is False


def test_i2_compose_not_last_fails():
    plan = _attribution_plan()
    compose = plan.pop()
    plan.insert(1, compose)
    assert validate_plan_invariants(plan) is False


def test_i3_analyze_requires_prior_retrieve_fails():
    plan = [
        {"id": "t1", "type": "analyze", "goal": "分析", "assigned_agent": "Analyst"},
        {"id": "t2", "type": "critique", "goal": "质检", "assigned_agent": "Critic"},
        {"id": "t3", "type": "compose", "goal": "汇总", "assigned_agent": "Composer"},
    ]
    assert validate_plan_invariants(plan) is False


def test_i4_analyze_requires_critique_fails():
    plan = _attribution_plan()
    plan = [p for p in plan if p["type"] != "critique"]
    assert validate_plan_invariants(plan) is False


def test_i4_critique_before_analyze_fails():
    plan = _attribution_plan()
    types = [p["type"] for p in plan]
    a, c = types.index("analyze"), types.index("critique")
    plan[a], plan[c] = plan[c], plan[a]
    assert validate_plan_invariants(plan) is False


def test_i5_phantom_l3_id_fails():
    assert validate_plan_invariants(_attribution_plan(targets=["l3-9-9-9"])) is False


def test_i5_empty_target_l3_fails():
    plan = _attribution_plan()
    plan[1]["target_l3"] = []
    assert validate_plan_invariants(plan) is False


def test_i6_rag_on_structured_table_fails():
    plan = [
        {
            "id": "t1",
            "type": "retrieve",
            "goal": "错配",
            "target_l3": ["l3-2-1-4"],
            "retrieve_mode": "rag",
            "assigned_agent": "Retriever",
        },
        {"id": "t2", "type": "compose", "goal": "汇总", "assigned_agent": "Composer"},
    ]
    assert validate_plan_invariants(plan) is False


def test_i6_structured_on_document_table_fails():
    plan = [
        {
            "id": "t1",
            "type": "retrieve",
            "goal": "错配",
            "target_l3": ["l3-1-1-1"],
            "retrieve_mode": "structured",
            "assigned_agent": "Retriever",
        },
        {"id": "t2", "type": "compose", "goal": "汇总", "assigned_agent": "Composer"},
    ]
    assert validate_plan_invariants(plan) is False


def test_i7_too_many_subtasks_fails():
    plan = _attribution_plan()
    for i in range(6):
        plan.insert(1, {
            "id": f"tx{i}",
            "type": "retrieve",
            "goal": "extra",
            "target_l3": ["l3-2-1-4"],
            "retrieve_mode": "structured",
            "assigned_agent": "Retriever",
        })
    assert len(plan) > 10
    assert validate_plan_invariants(plan) is False


def test_lookup_without_analyze_passes():
    plan = build_plan("lookup", "张三这个月请了几天假")
    assert validate_plan_invariants(plan) is True


def test_rules_fallback_plans_satisfy_invariants():
    for intent in ("policy", "lookup", "list", "aggregate", "trend", "forecast", "compare", "attribution"):
        plan = build_plan(intent, "杭抖部门近几个月离职率走势")
        assert validate_plan_invariants(plan), intent


def test_planner_rules_l3_ids_in_catalog():
    src = Path(__file__).resolve().parents[1] / "src" / "agent" / "planner_rules.py"
    text = src.read_text(encoding="utf-8")
    ids = set(re.findall(r"l3-\d+-\d+-\d+", text))
    catalog = valid_l3_ids()
    missing = ids - catalog
    assert not missing, f"planner_rules hardcoded IDs not in catalog: {missing}"
