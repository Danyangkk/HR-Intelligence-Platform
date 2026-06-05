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


def _plan_has_analyze(plan: list[dict[str, Any]]) -> bool:
    return any(item.get("type") == "analyze" for item in plan)


def _evidence_gaps_for_plan(state: AgentState, plan: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    evidence = state.get("evidence") or []
    for subtask in plan:
        if subtask.get("type") != "retrieve":
            continue
        mode = subtask.get("retrieve_mode") or "structured"
        for l3_id in subtask.get("target_l3") or []:
            if mode == "rag":
                hits = sum(
                    len(block.get("hits") or [])
                    for block in evidence
                    if block.get("kind") == "documents" and block.get("l3_id") == l3_id
                )
                if hits == 0:
                    gaps.append(f"missing: rag {l3_id}")
            else:
                rows = sum(
                    len(block.get("rows") or [])
                    for block in evidence
                    if block.get("kind") == "structured" and block.get("l3_id") == l3_id
                )
                if rows == 0:
                    gaps.append(f"missing: structured {l3_id}")
    return gaps


def _plan_evidence_checklist(plan: list[dict[str, Any]], state: AgentState) -> str:
    declared: list[str] = []
    for subtask in plan:
        if subtask.get("type") != "retrieve":
            continue
        mode = subtask.get("retrieve_mode") or "structured"
        for l3_id in subtask.get("target_l3") or []:
            declared.append(f"{mode} {l3_id}")
    actual: list[str] = []
    for block in state.get("evidence") or []:
        if block.get("kind") == "documents":
            actual.append(f"rag {block.get('l3_id')} hits={len(block.get('hits') or [])}")
        elif block.get("kind") == "structured":
            actual.append(f"structured {block.get('l3_id')} rows={len(block.get('rows') or [])}")
    return (
        f"计划声明取证路：{declared or '[]'}\n"
        f"实际证据块：{actual or '[]'}"
    )


def _finalize_critic(
    ctx,
    *,
    sufficient: bool,
    gaps: list[str],
    note: str,
    replan_count: int,
    plan: list[dict[str, Any]],
) -> dict[str, Any]:
    has_analyze = _plan_has_analyze(plan)
    needs_replan = (not sufficient) and replan_count < 2 and has_analyze
    limitation = ""

    if not sufficient and replan_count >= 2:
        sufficient = True
        needs_replan = False
        limitation = note or "证据不完整，以下结论仅供参考"
        ctx.run_step("evidence-validation", 3, "超限放行并声明局限")
    elif needs_replan:
        ctx.run_step("evidence-validation", 3, "证据不足，触发 replan")
    elif sufficient:
        ctx.run_step("evidence-validation", 3, "证据充分，继续 compose")

    trace_summary = note or (
        "证据充分" if sufficient and not needs_replan else f"需 replan：{','.join(gaps[:2])}"
    )
    ctx.run_step("evidence-validation", 2, trace_summary[:60])
    return {
        **ctx.to_state_patch(),
        "critic_sufficient": sufficient and not needs_replan,
        "critic_note": note or trace_summary,
        "limitation": limitation,
        "needs_replan": needs_replan,
        "replan_gaps": gaps if needs_replan else [],
        "trace": [ctx.trace_entry(subtask_id="critic", summary=trace_summary)],
    }


def _run_critic_llm(state: AgentState) -> dict[str, Any] | None:
    ctx = begin_agent_run("Critic", state, subtask_type="critique")
    ctx.run_step("evidence-validation", 1, "LLM 质检证据")

    plan = state.get("plan") or []
    analysis = state.get("analysis") or {}
    replan_count = state.get("replan_count") or 0
    checklist = _plan_evidence_checklist(plan, state)
    user = (
        f"intent={state.get('intent')}\n"
        f"replan_count={replan_count}\n"
        f"{checklist}\n"
        f"analysis_sufficient={analysis.get('sufficient')}\n"
        f"analysis_factors={len(analysis.get('factors') or [])}\n"
        f"analysis_reason={analysis.get('reason') or ''}\n"
        "按「计划声明 vs 实际证据」核对缺口，gaps 输出缺失路（如 missing: rag l3-1-3-3）。\n"
        '只输出 JSON：{"decision":"pass|replan|pass_with_limit","gaps":[],"note":""}'
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
    sufficient = decision == "pass"
    if decision == "pass_with_limit":
        sufficient = False
        note = note or "证据不完整，以下结论仅供参考"
    return _finalize_critic(
        ctx,
        sufficient=sufficient,
        gaps=gaps,
        note=note,
        replan_count=replan_count,
        plan=plan,
    )


def run_critic_rules(state: AgentState) -> dict[str, Any]:
    plan = state.get("plan") or []
    analysis = state.get("analysis") or {}
    replan_count = state.get("replan_count") or 0
    ctx = begin_agent_run("Critic", state, subtask_type="critique")
    ctx.run_step("evidence-validation", 1, "对照计划核对证据")

    gaps = _evidence_gaps_for_plan(state, plan)
    sufficient = not gaps
    note = "证据充分"

    if _plan_has_analyze(plan):
        if not analysis.get("sufficient"):
            sufficient = False
            note = analysis.get("reason") or "分析结论证据不足"
        if not (analysis.get("factors") or []) and state.get("intent") == "attribution":
            sufficient = False
            note = "未能找到足够归因因子"

    if gaps:
        sufficient = False
        note = f"取证缺口：{', '.join(gaps[:3])}"

    return _finalize_critic(
        ctx,
        sufficient=sufficient,
        gaps=gaps,
        note=note,
        replan_count=replan_count,
        plan=plan,
    )
