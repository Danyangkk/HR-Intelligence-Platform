from __future__ import annotations

from typing import Any

from src.agent.llm_runner import agent_llm_enabled, llm_json
from src.agent.prompts import CRITIC_SYSTEM
from src.agent.skills.runner import begin_agent_run
from src.agent.state import AgentState


def run_critic(state: AgentState) -> dict[str, Any]:
    if agent_llm_enabled():
        llm_result = _run_critic_llm(state)
        if llm_result is not None:
            return llm_result
    return run_critic_rules(state)


def _run_critic_llm(state: AgentState) -> dict[str, Any] | None:
    ctx = begin_agent_run("Critic", state, subtask_type="critique")
    ctx.run_step("evidence-validation", 1, "LLM 质检证据")

    evidence_count = len(state.get("evidence") or [])
    analysis = state.get("analysis") or {}
    user = (
        f"intent={state.get('intent')}\n"
        f"replan_count={state.get('replan_count') or 0}\n"
        f"evidence_blocks={evidence_count}\n"
        f"analysis_sufficient={analysis.get('sufficient')}\n"
        f"analysis_reason={analysis.get('reason') or ''}\n"
        "只输出 JSON：{\"decision\":\"pass|replan|pass_with_limit\",\"gaps\":[],\"note\":\"\"}"
    )
    payload = llm_json(
        agent="Critic",
        system=CRITIC_SYSTEM,
        user=user,
        state=state,
        subtask_type="critique",
    )
    if not payload:
        return None

    decision = str(payload.get("decision") or "pass").lower()
    gaps = list(payload.get("gaps") or [])
    note = str(payload.get("note") or "")
    replan_count = state.get("replan_count") or 0
    intent = state.get("intent")

    sufficient = decision == "pass"
    needs_replan = decision == "replan" and replan_count < 2 and intent in {"compare", "attribution"}
    limitation = ""
    if decision == "pass_with_limit" or (decision == "replan" and replan_count >= 2):
        sufficient = True
        needs_replan = False
        limitation = note or "证据不完整，以下结论仅供参考"
        ctx.run_step("evidence-validation", 3, "超限放行并声明局限")
    elif needs_replan:
        ctx.run_step("evidence-validation", 3, "证据不足，触发 replan")
    elif sufficient:
        ctx.run_step("evidence-validation", 3, "证据充分，继续 compose")

    trace_summary = note or ("证据充分" if sufficient and not needs_replan else f"需 replan：{','.join(gaps[:2])}")
    ctx.run_step("evidence-validation", 2, trace_summary[:60])
    return {
        **ctx.to_state_patch(),
        "critic_sufficient": sufficient and not needs_replan,
        "critic_note": note or trace_summary,
        "limitation": limitation,
        "needs_replan": needs_replan,
        "trace": [ctx.trace_entry(subtask_id="critic", summary=trace_summary)],
    }


def run_critic_rules(state: AgentState) -> dict[str, Any]:
    intent = state.get("intent")
    analysis = state.get("analysis") or {}
    replan_count = state.get("replan_count") or 0
    ctx = begin_agent_run("Critic", state, subtask_type="critique")
    ctx.run_step("evidence-validation", 1, f"检查 intent={intent} 所需 evidence")

    sufficient = True
    note = "证据充分"

    if intent in {"compare", "attribution"}:
        sufficient = bool(analysis.get("sufficient"))
        if not sufficient:
            note = analysis.get("reason") or "证据不足，建议补充数据或缩小范围"

    if intent == "compare":
        cost_rows = _count_rows(state, "l3-4-6-3")
        ctx.run_step("evidence-validation", 2, f"校验成本表行数：{cost_rows}")
        if cost_rows == 0:
            sufficient = False
            note = "缺少事业部成本拆分数据"

    if intent == "attribution":
        factors = analysis.get("factors") or []
        ctx.run_step("evidence-validation", 2, f"校验归因因子：{len(factors)} 条")
        if not factors:
            sufficient = False
            note = "未能找到足够归因因子"

    if intent == "trend":
        points = len((state.get("charts") or [{}])[0].get("data") or []) if state.get("charts") else 0
        ctx.run_step("evidence-validation", 2, f"校验趋势点数：{points}")
        sufficient = bool(analysis.get("sufficient"))
        if not sufficient:
            note = analysis.get("reason") or "趋势数据点不足"

    if intent == "forecast":
        ctx.run_step("evidence-validation", 2, "校验编制预测证据")
        sufficient = bool(analysis.get("sufficient"))
        if not sufficient:
            note = analysis.get("reason") or "缺少编制数据"

    if intent == "policy":
        doc_hits = _count_doc_hits(state)
        ctx.run_step("evidence-validation", 2, f"校验文档命中：{doc_hits} 段")
        if doc_hits == 0:
            sufficient = False
            note = "制度文档无命中"

    if not sufficient and replan_count >= 2:
        note = "已达 replan 上限，将基于现有证据作答并声明局限"
        sufficient = True
        limitation = "证据不完整，以下结论仅供参考"
        ctx.run_step("evidence-validation", 3, "replan 上限已达，声明局限后放行")
    else:
        limitation = "" if sufficient else ""
        if not sufficient and replan_count < 2 and intent in {"compare", "attribution", "trend"}:
            ctx.run_step("evidence-validation", 3, "证据不足，触发 replan")
        elif sufficient:
            ctx.run_step("evidence-validation", 3, "证据充分，继续 compose")

    needs_replan = not sufficient and replan_count < 2 and intent in {"compare", "attribution", "trend"}
    trace_summary = note if sufficient and not needs_replan else f"需 replan：{note}"
    return {
        **ctx.to_state_patch(),
        "critic_sufficient": sufficient and not needs_replan,
        "critic_note": note,
        "limitation": limitation,
        "needs_replan": needs_replan,
        "trace": [ctx.trace_entry(subtask_id="critic", summary=trace_summary)],
    }


def _count_rows(state: AgentState, l3_id: str) -> int:
    total = 0
    for block in state.get("evidence") or []:
        if block.get("l3_id") == l3_id:
            total += len(block.get("rows") or [])
    return total


def _count_doc_hits(state: AgentState) -> int:
    total = 0
    for block in state.get("evidence") or []:
        if block.get("kind") == "documents":
            total += len(block.get("hits") or [])
    return total
