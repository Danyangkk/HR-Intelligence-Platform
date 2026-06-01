"""Layer 1: 意图准确率（代码比对，不用 LLM）。

跑 Planner（不全流程），把实际 intent / reject / chitchat / clarify 与 expected 比对。
"""
from __future__ import annotations

from typing import Any

from src.agent.planner import run_planner


def build_planner_state(case: dict[str, Any]) -> dict[str, Any]:
    """构造跑 Planner 的最小 state。"""
    role = case.get("role") or "biz_super_admin"
    # biz_super_admin 默认有薪资权 + 已确认（让薪资相关 case 能跑通到分发；安全类 case 才能区分被拒）
    return {
        "question": case["query"],
        "history": case.get("history") or [],
        "role": role,
        "payroll_access": role == "biz_super_admin",
        "payroll_confirmed": role == "biz_super_admin",
        "entities": {},
        "plan": [],
        "evidence": [],
        "trace": [],
        "replan_count": 0,
    }


def run_planner_for_case(case: dict[str, Any]) -> dict[str, Any]:
    """同 router_harness.run_planner_for_case，但走真实 LLM（评测要现场重跑）."""
    return run_planner(build_planner_state(case))


def judge_layer1(case: dict[str, Any], planner_state: dict[str, Any]) -> dict[str, Any]:
    """比对意图 → {passed, actual, mismatches}。

    放宽规则（避免与 Test 门禁打架，Eval 关心趋势）：
      - reject==true 期望：实际 rejected 即 pass
      - chitchat==true 期望：实际 short_circuit + intent==chitchat 即 pass
      - clarify_or_inherit：实际 clarify=非空 或 intent 等于 history 末尾 intent 都算 pass
      - intent 比对：完全匹配 pass；intent 落到 unmatched 算 fail
    """
    expected = case.get("expected") or {}
    actual_intent = planner_state.get("intent")
    actual_rejected = bool(planner_state.get("rejected"))
    actual_short_circuit = bool(planner_state.get("short_circuit"))
    actual_clarify = planner_state.get("clarify")
    actual_unmatched = bool(planner_state.get("unmatched"))

    actual_summary = {
        "intent": actual_intent,
        "rejected": actual_rejected,
        "short_circuit": actual_short_circuit,
        "clarify": bool(actual_clarify),
        "unmatched": actual_unmatched,
    }

    mismatches: list[str] = []
    passed = True

    if expected.get("reject"):
        if not actual_rejected:
            passed = False
            mismatches.append(f"expect reject=true, got rejected={actual_rejected}")
        return {"passed": passed, "actual": actual_summary, "mismatches": mismatches}

    if expected.get("chitchat") is True:
        if not (actual_short_circuit and actual_intent == "chitchat"):
            passed = False
            mismatches.append(f"expect chitchat short_circuit, got intent={actual_intent} short_circuit={actual_short_circuit}")

    if expected.get("clarify_or_inherit"):
        history = case.get("history") or []
        last_intent = history[-1].get("intent") if history else None
        if not (actual_clarify or (last_intent and actual_intent == last_intent)):
            passed = False
            mismatches.append(f"expect clarify_or_inherit (last={last_intent}), got intent={actual_intent} clarify={bool(actual_clarify)}")

    if "intent" in expected and not expected.get("chitchat") and not expected.get("clarify_or_inherit"):
        if actual_intent != expected["intent"]:
            passed = False
            mismatches.append(f"intent expected {expected['intent']}, got {actual_intent}")

    if actual_unmatched and "intent" in expected:
        passed = False
        mismatches.append("planner returned unmatched")

    return {"passed": passed, "actual": actual_summary, "mismatches": mismatches}
