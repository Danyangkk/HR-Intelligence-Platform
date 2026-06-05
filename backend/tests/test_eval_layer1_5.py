from __future__ import annotations

from src.agent.planner_rules import build_plan
from src.eval.layer1_5 import judge_plan_compliance


def test_layer15_passes_valid_rules_plan():
    state = {"intent": "attribution", "plan": build_plan("attribution", "为什么运营组离职率偏高")}
    result = judge_plan_compliance(state)
    assert result["passed"] is True
    assert result.get("skipped") is not True


def test_layer15_skips_reject():
    result = judge_plan_compliance({"rejected": True, "plan": []})
    assert result["passed"] is True
    assert result.get("skipped") is True


def test_layer15_fails_invalid_plan():
    plan = build_plan("lookup", "张三请了几天假")
    plan[1]["target_l3"] = ["l3-9-9-9"]
    result = judge_plan_compliance({"intent": "lookup", "plan": plan})
    assert result["passed"] is False
