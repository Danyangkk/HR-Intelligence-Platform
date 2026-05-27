from __future__ import annotations

import pytest

from src.agent.planner import (
    build_orch_summary,
    build_plan,
    check_salary_rejection,
    classify_intent,
    run_planner,
)
from src.agent.planner_llm import _validate_plan, plan_with_rules, resolve_plan


def test_classify_resignation_procedure_is_policy():
    assert classify_intent("离职需要做哪些动作") == "policy"


def test_classify_attribution_still_works():
    assert classify_intent("为什么运营组离职率偏高") == "attribution"


def test_classify_personal_leave_is_lookup():
    assert classify_intent("张三11月请了几天假") == "lookup"


def test_classify_performance_lookup_rules():
    assert classify_intent("李四最近表现怎么样") == "lookup"


def test_build_orch_summary_distinguishes_rag_and_structured():
    rag = build_orch_summary("policy", "离职需要做哪些动作")
    structured = build_orch_summary("lookup", "张三11月请了几天假")
    assert "RAG" in rag
    assert "结构化" in structured


def test_build_plan_policy_topic_from_question():
    plan = build_plan("policy", "入职流程是什么")
    assert any("入职" in item["goal"] for item in plan)


def test_build_plan_lookup_uses_employee_name():
    plan = build_plan("lookup", "张三11月请了几天假")
    assert any("张三" in item["goal"] for item in plan)


def test_build_plan_performance_lookup():
    plan = build_plan("lookup", "李四最近表现怎么样")
    assert any("绩效" in item["goal"] for item in plan)
    assert any(item.get("target_l3") == ["l3-5-1-1"] for item in plan if item.get("type") == "retrieve")


def test_classify_policy_intent():
    assert classify_intent("年假怎么算") == "policy"
    assert classify_intent("入职流程是什么") == "policy"


def test_classify_does_not_inherit_lookup_hint_for_new_topic():
    assert classify_intent("入职流程是什么", hint="lookup") == "policy"


def test_classify_lookup_intent():
    assert classify_intent("张三11月请了几天假") == "lookup"


def test_salary_rejection():
    reason = check_salary_rejection("张三的工资条是多少")
    assert reason is not None
    assert "薪资明细" in reason


def test_salary_department_allowed():
    assert check_salary_rejection("各部门人均成本对比") is None


def test_planner_reject_state():
    state = run_planner({"question": "每个人的薪资明细"})
    assert state["rejected"] is True
    assert state.get("final")


def test_validate_plan_rejects_personal_policy():
    plan = build_plan("policy", "李四最近表现怎么样")
    assert _validate_plan("policy", plan, "李四最近表现怎么样") is False


def test_resolve_plan_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr("src.agent.planner_llm.plan_with_llm", lambda *a, **k: None)
    out = resolve_plan("李四最近表现怎么样")
    assert out["source"] == "rules"
    assert out["intent"] == "lookup"


def test_resolve_plan_uses_llm_when_valid(monkeypatch):
    llm_plan = plan_with_rules("李四最近表现怎么样")
    llm_plan["source"] = "llm"
    llm_plan["reasoning"] = "查员工绩效数据"
    monkeypatch.setattr("src.agent.planner_llm.plan_with_llm", lambda *a, **k: llm_plan)
    out = resolve_plan("李四最近表现怎么样")
    assert out["source"] == "llm"
    assert out["intent"] == "lookup"
