"""Layer 1.5: 计划合规率（不变式校验，零 LLM 成本）。"""

from __future__ import annotations

from typing import Any

from src.agent.planner_llm import validate_plan_invariants


def judge_plan_compliance(planner_state: dict[str, Any]) -> dict[str, Any]:
    """对 Planner 产出的 plan 跑不变式校验器。"""
    if planner_state.get("rejected") or planner_state.get("short_circuit"):
        return {
            "passed": True,
            "skipped": True,
            "reason": "reject_or_chitchat",
            "actual": {"plan_steps": 0},
        }

    plan = planner_state.get("plan") or []
    if not plan:
        if planner_state.get("unmatched"):
            return {
                "passed": False,
                "skipped": False,
                "reason": "unmatched_no_plan",
                "actual": {"plan_steps": 0},
            }
        return {
            "passed": True,
            "skipped": True,
            "reason": "empty_plan_allowed",
            "actual": {"plan_steps": 0},
        }

    passed = validate_plan_invariants(plan)
    types = [str(item.get("type")) for item in plan if item.get("type")]
    return {
        "passed": passed,
        "skipped": False,
        "actual": {
            "plan_steps": len(plan),
            "subtask_types": types,
            "invariants_ok": passed,
        },
    }
