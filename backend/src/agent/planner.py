from __future__ import annotations

import asyncio
from typing import Any

from src.agent.clarify_helpers import pick_payroll_l3s
from src.agent.planner_llm import planner_trace_summary, resolve_plan
from src.agent.planner_rules import (
    CHITCHAT_GREETING_REPLY,
    INTENT_UNMATCHED_MESSAGE,
    build_orch_summary,
    build_plan,
    classify_intent,
    extract_org,
    payroll_safety_net,
    route_payroll_by_scope,
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
    role = str(state.get("role") or "staff")
    payroll_confirmed = bool(state.get("payroll_confirmed"))

    from src.services.rbac import should_reject_personal_salary_query, normalize_role
    import sys

    role_normalized = normalize_role(role)
    print(
        f"[Planner] role={role_normalized}, payroll_confirmed={payroll_confirmed}",
        file=sys.stderr,
    )

    inherited = inherit_context(state)
    ctx = begin_agent_run("Planner", state)
    ctx.run_step("intent-planning", 1, "读问题与历史上下文")

    # === 主路径：调 LLM 做语义判定（intent + payroll_sensitive + payroll_scope + clarify）===
    resolved = await asyncio.to_thread(
        resolve_plan,
        question,
        history=state.get("history"),
        intent_hint=inherited.get("intent_hint"),
        entities=inherited.get("entities"),
    )
    print(f"\n[Planner resolve_plan] question={question[:50]}", file=sys.stderr)
    print(f"[Planner resolve_plan] unmatched={resolved.get('unmatched')}", file=sys.stderr)
    print(f"[Planner resolve_plan] chitchat={resolved.get('chitchat')}", file=sys.stderr)
    print(f"[Planner resolve_plan] intent={resolved.get('intent')}", file=sys.stderr)
    print(f"[Planner resolve_plan] source={resolved.get('source')}", file=sys.stderr)
    print(f"[Planner resolve_plan] payroll_sensitive={resolved.get('payroll_sensitive')}", file=sys.stderr)
    print(f"[Planner resolve_plan] payroll_scope={resolved.get('payroll_scope')}", file=sys.stderr)
    print(f"[Planner resolve_plan] reasoning={resolved.get('reasoning')}", file=sys.stderr)
    print(f"[Planner resolve_plan] plan_steps={len(resolved.get('plan') or [])}", file=sys.stderr)

    # === 薪资敏感判定：LLM 主判 + 关键词安全网（仅严不松）===
    llm_payroll_sensitive = bool(resolved.get("payroll_sensitive"))
    llm_payroll_scope = resolved.get("payroll_scope")  # individual / bu / company / None

    safety_net_hit = (not llm_payroll_sensitive) and payroll_safety_net(question)
    if safety_net_hit:
        print(
            f"[Planner] ⚠️  关键词安全网命中（LLM 未标 payroll_sensitive）-> 按可能涉密处理",
            file=sys.stderr,
        )

    is_payroll_sensitive = llm_payroll_sensitive or safety_net_hit

    if is_payroll_sensitive:
        # —— 角色权限决策（在 Python 层做，LLM 不感知 role/confirmed）——
        # ⚠️ 注意 reject 有两种：
        # 1) 真 reject（无权角色，含 tech_super_admin 纵深防御）→ 显示拒答话术，到此为止
        # 2) 可挽回 reject（业务超管未确认）→ 带 need_payroll_confirm 标识，
        #    前端识别后弹二次确认窗，确认后带 token 重发
        if should_reject_personal_salary_query(role_normalized):
            # 无权角色（普通员工 / 技术超管）→ 真 reject（显示拒答话术）
            # tech_super_admin 路径：前端本就看不到薪资入口，此处是防绕过的纵深防御。
            print(
                f"[Planner] ❌ 薪资敏感 + 无权角色({role_normalized}) -> 真 reject 拒答",
                file=sys.stderr,
            )
            reason = "该问题涉及个人薪资明细，依据安全规则无法回答。"
            return {
                **ctx.to_state_patch(),
                "rejected": True,
                "reject_reason": reason,
                "need_payroll_confirm": False,  # 真 reject，不可挽回
                "final": reason,
                "trace": [ctx.trace_entry(subtask_id="planner", summary=f"薪资敏感拦截：无权角色 {role_normalized}")],
            }

        if role_normalized == "biz_super_admin" and not payroll_confirmed:
            # 业务超管未确认 → 可挽回 reject（前端弹确认窗，确认后带 token 重发）
            print(f"[Planner] ⚠️  薪资敏感 + 业务超管未确认 -> 需要二次确认（可挽回）", file=sys.stderr)
            return {
                **ctx.to_state_patch(),
                "rejected": True,
                "reject_reason": "需要二次确认",
                "need_payroll_confirm": True,  # 显式标识：前端据此弹确认窗
                "final": "需要二次确认",
                "trace": [ctx.trace_entry(subtask_id="planner", summary="薪资敏感：要求二次确认")],
            }

        # 业务超管已确认 → 按 scope 分流（ROUTER §4 出口2）
        # 安全网兜底命中时 LLM 没给 scope，按"更严"原则当作 company → clarify
        effective_scope = llm_payroll_scope if llm_payroll_scope in {"individual", "bu", "company"} else "company"
        print(f"[Planner] ✅ 薪资敏感 + 业务超管已确认 -> 范围={effective_scope}", file=sys.stderr)

        if effective_scope == "company":
            # company → clarify 出口
            print(f"[Planner] 🔀 走 clarify 出口（请用户选事业部）", file=sys.stderr)
            return {
                **ctx.to_state_patch(),
                "rejected": False,
                "intent": "clarify",
                "clarify": {
                    "question": "薪资明细查询范围较大，请选择要查看的事业部：",
                    "options": [
                        {"label": "杭综部门", "value": "杭综部门", "next_query": "杭综部门薪资明细", "kind": "bu"},
                        {"label": "杭抖部门", "value": "杭抖部门", "next_query": "杭抖部门薪资明细", "kind": "bu"},
                        {"label": "职能部门", "value": "职能部门", "next_query": "职能部门薪资明细", "kind": "bu"},
                    ],
                    "kind": "bu",
                },
                "short_circuit": True,
                "final": "薪资明细查询范围较大，请选择要查看的事业部",
                "trace": [ctx.trace_entry(subtask_id="planner", summary="薪资明细范围过大，缩小到事业部")],
            }

        # individual / bu → 构造对应 plan（指向工资发放明细表 l3-4-1-4）
        intent_forced = "lookup" if effective_scope == "individual" else "list"
        entities = dict(inherited.get("entities") or {})
        if effective_scope == "bu":
            org_info = extract_org(question)
            bu_name = org_info.get("事业部")
            if bu_name:
                entities["org"] = {**entities.get("org", {}), "事业部": bu_name}

        # 按问题里提到的具体薪酬字段（工资/奖金/社保/股权）动态选 L3 表集；
        # 宽泛"薪资/薪酬"问法默认查工资+奖金+社保三张明细主表。Retriever 按工号/事业部筛。
        target_l3s = pick_payroll_l3s(question)
        print(f"[Planner] 薪资目标表集: {target_l3s}", file=sys.stderr)

        if intent_forced == "list":
            bu_name = (entities.get("org") or {}).get("事业部")
            plan = [
                {
                    "id": "t1",
                    "type": "retrieve",
                    "goal": f"取 {bu_name or '指定范围'} 全员薪资明细（按事业部筛）",
                    "target_l3": target_l3s,
                    "assigned_agent": "Retriever",
                    "retrieve_mode": "structured",
                },
                {
                    "id": "t2",
                    "type": "compose",
                    "goal": "组织薪资明细答案并标注数据来源",
                    "assigned_agent": "Composer",
                },
            ]
        else:
            plan = [
                {"id": "t1", "type": "resolve", "goal": "解析员工到工号", "assigned_agent": "Resolver"},
                {
                    "id": "t2",
                    "type": "retrieve",
                    "goal": "取该员工薪资明细（按工号筛）",
                    "target_l3": target_l3s,
                    "assigned_agent": "Retriever",
                    "retrieve_mode": "structured",
                },
                {"id": "t3", "type": "compose", "goal": "组织个人薪资答案并标注数据来源", "assigned_agent": "Composer"},
            ]

        ctx.run_step("intent-planning", 2, f"薪资语义命中 scope={effective_scope} -> intent={intent_forced}")
        ctx.run_step("intent-planning", 3, f"生成 plan {len(plan)} 步")
        ctx.run_step("intent-planning", 4, "交由 Supervisor 派发")
        summary = planner_trace_summary(
            intent_forced, question, reasoning=f"薪资范围={effective_scope}", source="payroll-llm"
        )
        return {
            **ctx.to_state_patch(),
            "intent": intent_forced,
            "plan": plan,
            "entities": entities,
            "rejected": False,
            "broaden_search": False,
            "trace": [ctx.trace_entry(subtask_id="planner", summary=summary)],
        }

    # === 非薪资敏感：走正常路径 ===
    # 处理 LLM 直接返回 clarify 出口（如多解需澄清）的情况
    if resolved.get("intent") == "clarify" and resolved.get("clarify"):
        return {
            **ctx.to_state_patch(),
            "rejected": False,
            "intent": "clarify",
            "clarify": resolved.get("clarify"),
            "short_circuit": True,
            "final": (resolved.get("clarify") or {}).get("question") or "需要补充信息",
            "trace": [ctx.trace_entry(subtask_id="planner", summary="LLM 主动 clarify")],
        }

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
