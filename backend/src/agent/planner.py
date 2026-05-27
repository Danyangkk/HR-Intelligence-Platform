from __future__ import annotations

import asyncio
from typing import Any

from src.agent.planner_llm import planner_trace_summary, resolve_plan
from src.agent.planner_rules import (
    CHITCHAT_GREETING_REPLY,
    INTENT_UNMATCHED_MESSAGE,
    build_orch_summary,
    build_plan,
    check_salary_rejection,
    classify_intent,
    extract_org,
)
from src.agent.skills.runner import SkillRunContext, begin_agent_run
from src.agent.state import AgentState, Intent

from src.agent.planner_rules import NAME_RE as _NAME_RE


def inherit_context(state: AgentState) -> dict[str, Any]:
    history = state.get("history") or []
    entities: dict[str, Any] = dict(state.get("entities") or {})
    intent_hint: str | None = None
    if history:
        last = history[-1]
        if last.get("entities"):
            entities = {**last.get("entities", {}), **entities}
        intent_hint = last.get("intent")
    return {"entities": entities, "intent_hint": intent_hint}


def run_planner(state: AgentState) -> dict[str, Any]:
    """Sync wrapper for tests."""
    return asyncio.run(run_planner_async(state))


async def run_planner_async(state: AgentState) -> dict[str, Any]:
    question = state["question"]
    reject_reason = check_salary_rejection(question)
    if reject_reason:
        return {
            "rejected": True,
            "reject_reason": reject_reason,
            "final": reject_reason,
            "trace": [{"subtask_id": "planner", "agent": "Planner", "summary": "敏感校验命中：个人薪资明细"}],
        }

    inherited = inherit_context(state)
    ctx = begin_agent_run("Planner", state)
    ctx.run_step("intent-planning", 1, "读问题与历史上下文")

    resolved = await asyncio.to_thread(
        resolve_plan,
        question,
        history=state.get("history"),
        intent_hint=inherited.get("intent_hint"),
        entities=inherited.get("entities"),
    )
    if resolved.get("unmatched"):
        return {
            **ctx.to_state_patch(),
            "rejected": True,
            "unmatched": True,
            "reject_reason": INTENT_UNMATCHED_MESSAGE,
            "final": INTENT_UNMATCHED_MESSAGE,
            "trace": [
                ctx.trace_entry(
                    subtask_id="planner",
                    summary="未匹配业务意图或置信度过低，直接友好回复",
                )
            ],
        }

    if resolved.get("chitchat"):
        reply = resolved.get("reply") or CHITCHAT_GREETING_REPLY
        return {
            **ctx.to_state_patch(),
            "intent": "chitchat",
            "plan": [],
            "final": reply,
            "short_circuit": True,
            "rejected": False,
            "trace": [
                ctx.trace_entry(
                    subtask_id="planner",
                    summary="闲聊短路，直接回复",
                )
            ],
        }

    intent: Intent | str = resolved["intent"]
    plan = resolved["plan"]
    reasoning = resolved.get("reasoning") or ""
    source = resolved.get("source") or "rules"

    ctx.run_step("intent-planning", 2, f"识别意图 {intent}（{source}）")
    ctx.run_step("intent-planning", 3, f"生成 plan {len(plan)} 步")
    ctx.run_step("intent-planning", 4, "交由 Supervisor 按 plan 派发")

    entities = inherited["entities"]
    if intent in {"compare", "attribution", "list", "aggregate", "trend", "forecast"}:
        entities = {**entities, "org": extract_org(question)}

    replan = state.get("replan_count") or 0
    summary = planner_trace_summary(intent, question, reasoning=reasoning, source=source)
    if replan:
        summary += f"（第 {replan + 1} 轮）"
    trace_entry = ctx.trace_entry(subtask_id="planner", summary=summary)
    return {
        **ctx.to_state_patch(),
        "intent": intent,
        "plan": plan,
        "entities": entities,
        "rejected": False,
        "broaden_search": bool(state.get("broaden_search")),
        "trace": [trace_entry],
    }
