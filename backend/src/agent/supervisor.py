"""Supervisor — dispatch subtasks from Planner plan via tools layer."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END
from langgraph.types import Send
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.retriever_llm import suggest_relaxed_filters
from src.agent.skills.runner import begin_agent_run
from src.agent.state import AgentState
from src.agent.tools.registry import invoke_tool
from src.db.session import AsyncSessionLocal
from src.models import Template
from src.services.rbac import guard_evidence_blocks as _guard_evidence

HANDBOOK_L3 = "l3-1-1-1"
ROSTER_L3 = "l3-2-1-4"
COST_L3 = "l3-4-6-3"
HEADCOUNT_L3 = "l3-6-1-1"

# 员工粒度表：个人归因/查人时必须按工号过滤
_EMPLOYEE_ROW_L3 = frozenset(
    {
        "l3-2-2-1",
        "l3-2-2-2",
        "l3-2-2-3",
        "l3-2-2-4",
        "l3-2-2-5",
        "l3-2-2-6",
        "l3-2-2-7",
        "l3-2-3-1",
        "l3-5-1-1",
        "l3-5-2-1",
    }
)


def _employee_id(state: AgentState) -> str:
    employee = (state.get("entities") or {}).get("employee") or {}
    return str(employee.get("工号") or "").strip()


def _personal_employee_scope(state: AgentState) -> bool:
    """Resolved employee on attribution/lookup — fetch & cite only that person."""
    if not _employee_id(state):
        return False
    return state.get("intent") in {"lookup", "attribution"}


def _retrieve_worker_payload(state: AgentState, l3_id: str) -> dict[str, Any]:
    """LangGraph Send replaces worker input — must carry resolver entities for filters
    AND payroll权限标志（业务超管薪资表查询需要 payroll_confirmed=True 才能解密）."""
    payload: dict[str, Any] = {
        "fetch_l3_id": l3_id,
        "question": state.get("question"),
        "intent": state.get("intent"),
        "role": state.get("role"),
        "payroll_access": state.get("payroll_access"),
        "payroll_confirmed": state.get("payroll_confirmed"),
        "broaden_search": state.get("broaden_search"),
        "plan": state.get("plan"),
        "plan_index": state.get("plan_index"),
    }
    entities = state.get("entities")
    if entities:
        payload["entities"] = dict(entities)
    return payload


def _filter_rows_for_employee(state: AgentState, l3_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    emp_id = _employee_id(state)
    if not emp_id or not _personal_employee_scope(state):
        return rows
    if l3_id not in _EMPLOYEE_ROW_L3:
        return rows
    return [row for row in rows if str(row.get("工号") or "") == emp_id]


def get_current_subtask(state: AgentState) -> dict[str, Any] | None:
    plan = state.get("plan") or []
    idx = state.get("plan_index") or 0
    if idx >= len(plan):
        return None
    return plan[idx]


def advance_plan(state: AgentState, *, steps: int = 1) -> int:
    return (state.get("plan_index") or 0) + steps


def retrieve_targets_for_state(state: AgentState) -> list[str]:
    subtask = get_current_subtask(state) or {}
    targets = subtask.get("target_l3") or []
    if not targets:
        entities = state.get("entities") or {}
        if entities.get("target_l3"):
            return list(entities["target_l3"])
        targets = _default_structured_targets(state.get("intent"), entities=entities)
    return targets


def supervisor_dispatch(state: AgentState) -> str | list[Send]:
    """Route plan subtask; multi-table structured retrieve uses LangGraph Send fan-out."""
    route = route_after_supervisor(state)
    if route == "end":
        return END
    if route != "retrieve":
        return route
    subtask = get_current_subtask(state) or {}
    if (subtask.get("retrieve_mode") or "structured") == "rag":
        return "document"
    targets = retrieve_targets_for_state(state)
    if len(targets) > 1:
        return [Send("retrieve_worker", _retrieve_worker_payload(state, l3_id)) for l3_id in targets]
    return "retrieve"


def route_after_supervisor(state: AgentState) -> str:
    if state.get("rejected"):
        return "end"
    if state.get("clarify"):
        return "composer"
    subtask = get_current_subtask(state)
    if not subtask:
        return "composer"
    stype = subtask.get("type")
    if stype == "compose":
        return "composer"
    if stype == "resolve":
        return "resolver"
    if stype == "retrieve":
        mode = subtask.get("retrieve_mode") or "structured"
        return "document" if mode == "rag" else "retrieve"
    if stype == "analyze":
        return "analyst"
    if stype == "critique":
        return "critic"
    return "composer"


def supervisor_trace_entry(state: AgentState) -> dict[str, Any]:
    subtask = get_current_subtask(state)
    if not subtask:
        ctx = begin_agent_run("Planner", state)
        ctx.run_step("intent-planning", 4, "plan 已全部执行，进入 Composer")
        return ctx.trace_entry(subtask_id="supervisor", summary="计划执行完毕，进入 Composer", agent="Supervisor")

    assigned = subtask.get("assigned_agent") or "Agent"
    ctx = begin_agent_run(assigned, state, subtask_type=subtask.get("type"))
    skill_id = ctx.skills[0]["id"] if ctx.skills else "intent-planning"
    target = subtask.get("target_l3") or []
    target_hint = f" → {','.join(target[:3])}" if target else ""
    goal = subtask.get("goal", "")[:48]
    ctx.run_step(skill_id, 1, f"按 plan 派发 {subtask.get('type')} 给 {assigned}{target_hint}")
    return ctx.trace_entry(
        subtask_id=subtask.get("id") or "supervisor",
        summary=f"派发 {subtask.get('type')} 给 {assigned}{target_hint}：{goal}",
        agent="Supervisor",
    )


async def _prefetch_retriever_tools(
    ctx,
    db: AsyncSession,
    l3_id: str,
) -> None:
    from src.services.source import source_of

    ctx.record_tool("get_template")
    tpl = await invoke_tool("get_template", db, l3_id=l3_id)
    col_n = len(tpl.get("columns") or [])
    ctx.run_step("structured-retrieval", 1, f"get_template · {col_n} 列")
    if source_of(l3_id) == "feishu":
        ctx.record_tool("feishu_status")
        status = await invoke_tool("feishu_status", db, l3_id=l3_id)
        ctx.run_step("structured-retrieval", 1, f"feishu_status · {status.get('status')}")


async def execute_retrieve_subtask(db: AsyncSession, state: AgentState, subtask: dict[str, Any]) -> dict[str, Any]:
    mode = subtask.get("retrieve_mode") or "structured"
    role = state.get("role") or "viewer"
    intent = state.get("intent")
    subtask_id = subtask.get("id") or "retrieve"
    ctx = begin_agent_run("Retriever", state, subtask_type="retrieve")

    if mode == "rag":
        l3_ids = subtask.get("target_l3") or [HANDBOOK_L3]
        l3_id = l3_ids[0]
        ctx.run_step("document-rag", 1, f"限定 l3_id={l3_id}")
        ctx.record_tool("search_documents")
        result = await invoke_tool(
            "search_documents",
            db,
            l3_id=l3_id,
            query=state["question"],
            top_k=5,
            only_current=True,
        )
        hits = result.get("hits") or []
        ctx.run_step("document-rag", 2, f"top_k 命中 {len(hits)} 段")
        evidence = [{"kind": "documents", "l3_id": l3_id, "hits": hits}]
        citations = [
            {
                "kind": "doc",
                "l3_id": l3_id,
                "doc_id": hit.get("doc_id") or hit.get("document_id"),
                "seq": hit.get("seq"),
                "title_path": hit.get("title_path"),
                "chunk": hit.get("text"),
                "score": hit.get("score"),
            }
            for hit in hits
        ]
        summary = f"RAG {l3_id} · 命中 {len(hits)} 段"
        ctx.run_step("document-rag", 3, "无命中不臆造" if not hits else "已组织 citations")
        return {
            **ctx.to_state_patch(),
            "evidence": evidence,
            "citations": citations,
            "trace": [ctx.trace_entry(subtask_id=subtask_id, summary=summary)],
        }

    target_l3 = subtask.get("target_l3") or []
    if not target_l3:
        target_l3 = _default_structured_targets(intent)
    ctx.run_step("structured-retrieval", 1, f"读 target_l3：{','.join(target_l3[:3])}")

    # 空表/无模板/取数异常时优雅降级返回 0 行 evidence，避免抛 IndexError 触发 wrapper 重试。
    # 复盘 trace 仍能记录 rows_returned=0，比 3 次 IndexError 更准确反映"取数 0 条"。
    if not target_l3:
        empty_block = {"kind": "structured", "l3_id": "", "rows": []}
        ctx.run_step("structured-retrieval", 2, "未配置 target_l3 → 0 条")
        return {
            **ctx.to_state_patch(),
            "evidence": [empty_block],
            "citations": [],
            "trace": [ctx.trace_entry(subtask_id=subtask_id, summary="未配置 target_l3")],
        }

    l3_id = target_l3[0]
    try:
        await _prefetch_retriever_tools(ctx, db, l3_id)
        ctx.record_tool("query_structured")
        fetched = await _fetch_l3(db, state, l3_id, role=role)
    except (IndexError, KeyError, AttributeError) as exc:
        import logging
        logging.getLogger("agent.harness").warning(
            "structured retrieve degraded for l3=%s: %s(%s)", l3_id, type(exc).__name__, exc
        )
        empty_block = {"kind": "structured", "l3_id": l3_id, "rows": []}
        ctx.run_step("structured-retrieval", 2, f"{l3_id} 取数异常({type(exc).__name__}) → 降级 0 条")
        return {
            **ctx.to_state_patch(),
            "evidence": [empty_block],
            "citations": [],
            "trace": [ctx.trace_entry(subtask_id=subtask_id, summary=f"{l3_id} 取数异常 → 降级 0 条")],
        }

    ctx.run_step("structured-retrieval", 2, fetched["summary"])
    guarded = _guard_evidence(
        [fetched["block"]],
        role=role,
        payroll_access=bool(state.get("payroll_access")),
        payroll_confirmed=bool(state.get("payroll_confirmed")),
    )
    ctx.run_step("pii-permission", 1, f"role={role} 脱敏后 {len(guarded[0].get('rows') or [])} 行")
    return {
        **ctx.to_state_patch(),
        "evidence": guarded,
        "citations": fetched["citations"],
        "trace": [ctx.trace_entry(subtask_id=subtask_id, summary=fetched["summary"])],
    }


def _default_structured_targets(intent: str | None, *, entities: dict[str, Any] | None = None) -> list[str]:
    entities = entities or {}
    if entities.get("target_l3"):
        return list(entities["target_l3"])
    if intent == "lookup":
        from src.agent.clarify_helpers import lookup_target_l3s

        scope = entities.get("lookup_scope")
        if scope:
            return lookup_target_l3s(str(scope))
        return ["l3-2-2-1"]
    if intent == "compare":
        return [COST_L3, HEADCOUNT_L3]
    if intent == "attribution":
        return ["l3-2-5-1", "l3-2-3-1", "l3-5-1-1"]
    if intent == "aggregate":
        return ["l3-2-2-1"]
    if intent == "list":
        return ["l3-2-1-4"]
    if intent == "trend":
        return ["l3-2-5-1"]
    if intent == "forecast":
        return ["l3-6-1-1"]
    return ["l3-2-2-1"]


async def run_retrieve_worker(state: AgentState) -> dict[str, Any]:
    """LangGraph Send worker — one l3_id per instance."""
    l3_id = state.get("fetch_l3_id") or ""
    role = state.get("role") or "viewer"
    subtask = get_current_subtask(state) or {}
    subtask_id = subtask.get("id") or "retrieve"
    ctx = begin_agent_run("Retriever", state, subtask_type="retrieve")
    ctx.run_step("structured-retrieval", 1, f"Send worker 取数 {l3_id}")

    # 与 execute_retrieve_subtask 同样的容错：单 worker 取数异常时优雅降级，
    # 不让一张表的 IndexError 把整个 fan-out 拖崩。其他并行 worker 的结果仍能合并。
    try:
        async with AsyncSessionLocal() as db:
            await _prefetch_retriever_tools(ctx, db, l3_id)
            ctx.record_tool("query_structured")
            fetched = await _fetch_l3(db, state, l3_id, role=role, skip_prefetch=True)
    except (IndexError, KeyError, AttributeError) as exc:
        import logging
        logging.getLogger("agent.harness").warning(
            "Send worker structured retrieve degraded for l3=%s: %s(%s)",
            l3_id, type(exc).__name__, exc,
        )
        empty_block = {"kind": "structured", "l3_id": l3_id, "rows": []}
        ctx.run_step("structured-retrieval", 2, f"{l3_id} 取数异常({type(exc).__name__}) → 降级 0 条")
        return {
            **ctx.to_state_patch(include_active_skills=False),
            "evidence": [empty_block],
            "citations": [],
            "trace": [ctx.trace_entry(subtask_id=f"{subtask_id}-{l3_id}", summary=f"{l3_id} 取数异常 → 降级 0 条")],
        }

    ctx.run_step("structured-retrieval", 2, fetched["summary"])
    guarded = _guard_evidence(
        [fetched["block"]],
        role=role,
        payroll_access=bool(state.get("payroll_access")),
        payroll_confirmed=bool(state.get("payroll_confirmed")),
    )
    ctx.run_step("pii-permission", 1, f"role={role} 脱敏完成")
    return {
        **ctx.to_state_patch(include_active_skills=False),
        "evidence": guarded,
        "citations": fetched["citations"],
        "trace": [ctx.trace_entry(subtask_id=f"{subtask_id}-{l3_id}", summary=fetched["summary"])],
    }


async def run_retrieve_collect(state: AgentState) -> dict[str, Any]:
    """Aggregate Send workers and advance plan."""
    subtask = get_current_subtask(state) or {}
    targets = retrieve_targets_for_state(state)
    ctx = begin_agent_run("Retriever", state, subtask_type="retrieve")
    ctx.run_step("structured-retrieval", 2, f"Send 并行扇出 {len(targets)} 路完成")
    summary = f"Send 并行扇出 {len(targets)} 路取数完成"
    return {
        **ctx.to_state_patch(),
        "plan_index": advance_plan(state),
        "trace": [ctx.trace_entry(subtask_id=subtask.get("id") or "retrieve", summary=summary, agent="Supervisor")],
    }


async def _fetch_l3(
    db: AsyncSession,
    state: AgentState,
    l3_id: str,
    *,
    role: str,
    skip_prefetch: bool = False,
) -> dict[str, Any]:
    if not skip_prefetch:
        pass
    filters = _filters_for_l3(state, l3_id)
    subtask = get_current_subtask(state) or {}
    aggregations = subtask.get("aggregations") or []
    group_by = subtask.get("group_by") or []

    if aggregations:
        result = await invoke_tool(
            "query_structured",
            db,
            l3_id=l3_id,
            filters=filters,
            role=role,
            group_by=list(group_by),
            aggregations=list(aggregations),
            page_size=50,
        )
        rows = result.get("grouped_rows") or []
        if not rows and result.get("agg"):
            rows = [result["agg"]]
        block = {
            "kind": "structured",
            "l3_id": l3_id,
            "rows": rows,
            "agg": result.get("agg"),
            "mode": result.get("mode") or "aggregate",
            "group_by": group_by,
        }
        summary = f"{l3_id} 聚合 {len(rows)} 组"
        citations: list[dict[str, Any]] = []
        return {"block": block, "citations": citations, "summary": summary}

    result = await invoke_tool(
        "query_structured",
        db,
        l3_id=l3_id,
        filters=filters,
        page_size=50 if l3_id in {COST_L3, HEADCOUNT_L3, "l3-2-5-1", "l3-2-3-1", "l3-5-1-1", "l3-2-1-4", "l3-6-1-1"} else 20,
        role=role,
    )
    items = result.get("items") or []
    if not items and filters:
        tpl = await db.get(Template, l3_id)
        columns = list(tpl.columns) if tpl else []
        relaxed = await suggest_relaxed_filters(
            state,
            l3_id=l3_id,
            filters=filters,
            template_columns=columns,
        )
        if relaxed:
            retry = await invoke_tool(
                "query_structured",
                db,
                l3_id=l3_id,
                filters=relaxed,
                page_size=50 if l3_id in {COST_L3, HEADCOUNT_L3, "l3-2-5-1", "l3-2-3-1", "l3-5-1-1", "l3-2-1-4", "l3-6-1-1"} else 20,
                role=role,
            )
            items = retry.get("items") or []
    items = _filter_rows_for_employee(state, l3_id, items)
    block = {"kind": "structured", "l3_id": l3_id, "rows": items}
    citations = [{"kind": "data", "l3_id": l3_id, "locator": row.get("_locator") or []} for row in items[:10]]
    return {"block": block, "citations": citations, "summary": f"{l3_id} {len(items)} 条"}


def _filters_for_l3(state: AgentState, l3_id: str) -> dict[str, str]:
    entities = state.get("entities") or {}
    employee = entities.get("employee") or {}
    org = entities.get("org") or {}
    filters: dict[str, str] = {}

    if employee.get("工号") and l3_id in _EMPLOYEE_ROW_L3:
        filters["工号"] = str(employee["工号"])

    if l3_id == COST_L3 and not state.get("broaden_search"):
        month = org.get("统计月份") or "2025-10"
        filters["月份"] = month
    if l3_id == HEADCOUNT_L3:
        filters["统计月份"] = org.get("统计月份") or "2025-10"
    if l3_id == "l3-2-5-1":
        intent = state.get("intent")
        if intent in {"trend", "aggregate"} and not state.get("broaden_search"):
            bu = org.get("事业部")
            dept = org.get("部门")
            if bu:
                filters["事业部"] = str(bu)
            elif dept:
                filters["部门"] = str(dept)
        if intent != "trend":
            filters["统计周期"] = org.get("统计月份") or "2025-10"
            dept = org.get("部门") or employee.get("部门")
            if dept and not state.get("broaden_search") and not _personal_employee_scope(state) and not org.get("事业部"):
                filters["部门"] = str(dept)

    if l3_id == "l3-2-1-4":
        if org.get("部门"):
            filters["部门"] = str(org["部门"])
        elif org.get("事业部"):
            filters["事业部"] = str(org["事业部"])

    if l3_id == "l3-6-1-1":
        filters["统计月份"] = org.get("统计月份") or "2025-10"
        if org.get("事业部"):
            filters["事业部"] = str(org["事业部"])
        elif org.get("部门"):
            filters["部门"] = str(org["部门"])

    month = entities.get("time_range")
    if month and l3_id == "l3-2-2-1":
        if isinstance(month, dict):
            start = month.get("from") or month.get("start")
            if start:
                filters["开始日期"] = str(start)[:7]
        else:
            filters["开始日期"] = str(month)
    elif state.get("intent") == "aggregate" and l3_id == "l3-2-2-1":
        month = org.get("统计月份") or "2025-10"
        filters["开始日期"] = month

    return filters


async def run_retrieve_from_plan(db: AsyncSession, state: AgentState) -> dict[str, Any]:
    subtask = get_current_subtask(state) or {}
    result = await execute_retrieve_subtask(db, state, subtask)
    result["plan_index"] = advance_plan(state)
    return result


async def run_document_from_plan(db: AsyncSession, state: AgentState) -> dict[str, Any]:
    subtask = get_current_subtask(state) or {"retrieve_mode": "rag", "target_l3": [HANDBOOK_L3]}
    result = await execute_retrieve_subtask(db, state, subtask)
    result["plan_index"] = advance_plan(state)
    return result


# Backward-compatible alias used during migration
async def retrieve_for_intent(db: AsyncSession, state: AgentState) -> dict[str, Any]:
    subtask = get_current_subtask(state)
    if subtask and subtask.get("type") == "retrieve":
        return await run_retrieve_from_plan(db, state)
    intent = state.get("intent")
    fallback = {
        "type": "retrieve",
        "retrieve_mode": "rag" if intent == "policy" else "structured",
        "target_l3": _default_structured_targets(intent) if intent != "policy" else [HANDBOOK_L3],
        "id": "retrieve",
    }
    result = await execute_retrieve_subtask(db, state, fallback)
    return result
