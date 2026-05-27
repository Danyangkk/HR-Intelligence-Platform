"""Validate LLM/rules draft entities via DB + metric dictionary + structured clarify."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.clarify_helpers import (
    apply_clarify_option,
    build_scope_clarify,
    effective_lookup_question,
    is_vague_lookup_question,
    lookup_target_l3s,
    match_clarify_option,
)
from src.agent.metric_resolver import resolve_metric_from_text
from src.agent.planner_rules import NAME_RE as _NAME_RE, extract_list_filters, extract_org, is_org_metric_question
from src.agent.resolver_lookup import (
    EmployeeLookupResult,
    _extract_month,
    _lookup_clarify,
    _lookup_employee,
    _lookup_success,
)
from src.agent.state import AgentState
from src.core.constants import BU_UNITS


def _normalize_org(org: dict[str, Any] | None, question: str) -> dict[str, Any]:
    merged = dict(org or {})
    extracted = extract_org(question)
    for key, value in extracted.items():
        if value and not merged.get(key):
            merged[key] = value
    bu = merged.get("事业部")
    if bu and bu not in BU_UNITS:
        for unit in BU_UNITS:
            if unit in str(bu) or str(bu) in unit:
                merged["事业部"] = unit
                break
    return merged


def _normalize_time_range(value: Any) -> str | None:
    if isinstance(value, dict):
        start = value.get("from") or value.get("start")
        if start:
            return str(start)[:7]
        return None
    if value:
        text = str(value)
        if re.match(r"^\d{4}-\d{2}", text):
            return text[:7]
    return None


def _attach_metric(entities: dict[str, Any], question: str, metric_query: str = "") -> dict[str, Any]:
    if entities.get("metric"):
        return entities
    spec = resolve_metric_from_text(question, metric_query)
    if spec:
        entities = dict(entities)
        entities["metric"] = spec
    return entities


async def _resolve_employee_name(
    db: AsyncSession,
    ctx,
    entities: dict[str, Any],
    name: str,
) -> dict[str, Any] | None:
    ctx.record_tool("query_structured")
    lookup = await _lookup_employee(db, name)
    if lookup.kind == "found" and lookup.employee:
        entities = dict(entities)
        entities["employee"] = lookup.employee
        return _lookup_success(
            ctx,
            entities=entities,
            summary=f"{name} → 工号 {lookup.employee.get('工号')}",
        )
    if lookup.kind == "ambiguous":
        ctx.run_step("entity-resolution", 3, f"重名 {name}，请求澄清")
        return _lookup_clarify(
            ctx,
            clarify=lookup.clarify_payload(name),
            entities=entities,
            summary=f"重名需澄清：{name}",
        )
    ctx.run_step("entity-resolution", 3, f"未找到员工 {name}")
    return _lookup_clarify(
        ctx,
        clarify=EmployeeLookupResult(kind="not_found").clarify_payload(name),
        entities=entities,
        summary=f"未找到员工：{name}",
    )


async def finalize_resolver_entities(
    db: AsyncSession,
    state: AgentState,
    ctx,
    draft: dict[str, Any],
    *,
    metric_query: str = "",
    source: str = "rules",
) -> dict[str, Any]:
    """Single validation gate for LLM draft + rules partial entities."""
    intent = state.get("intent", "lookup")
    question = state.get("question") or ""
    entities = {**dict(state.get("entities") or {}), **dict(draft or {})}

    matched = match_clarify_option(question, state.get("history"))
    if matched:
        entities = apply_clarify_option(entities, matched)
        ctx.run_step("entity-resolution", 2, "继承澄清选项")

    entities = _attach_metric(entities, question, metric_query)
    tr = _normalize_time_range(entities.get("time_range"))
    if tr:
        entities["time_range"] = tr
    elif intent == "lookup":
        month = _extract_month(effective_lookup_question(state))
        if month:
            entities["time_range"] = month

    if intent == "compare":
        entities["org"] = _normalize_org(entities.get("org"), question)
        org = entities["org"]
        ctx.run_step("entity-resolution", 2, f"校验组织范围（{source}）")
        summary = f"组织范围：{org.get('事业部') or '全部事业部'} / {org.get('统计月份') or '2025-10'}"
        if entities.get("metric"):
            summary += f" · 指标 {entities['metric'].get('name')}"
        ctx.run_step("entity-resolution", 3, summary)
        return _lookup_success(ctx, entities=entities, summary=summary)

    if intent == "attribution":
        entities["org"] = _normalize_org(entities.get("org"), question)
        topic = entities.get("topic")
        if not topic:
            topic = "离职" if "离职" in question else "绩效" if "绩效" in question else "综合"
            entities["topic"] = topic

        employee = entities.get("employee") or {}
        if employee.get("姓名") and not employee.get("工号"):
            result = await _resolve_employee_name(db, ctx, entities, str(employee["姓名"]))
            if result.get("clarify"):
                return result
            entities = result.get("entities") or entities
        elif not employee.get("工号"):
            match = _NAME_RE.search(question)
            if match:
                result = await _resolve_employee_name(db, ctx, entities, match.group(0))
                if result.get("clarify"):
                    return result
                entities = result.get("entities") or entities

        org = entities.get("org") or {}
        summary = f"组织/主题：{org.get('部门') or org.get('事业部') or '全公司'} / {entities.get('topic')}"
        if entities.get("employee", {}).get("工号"):
            summary = f"{entities['employee'].get('姓名')} → {entities['employee'].get('工号')}；{summary}"
        if entities.get("metric"):
            summary += f" · 指标 {entities['metric']['name']}"
        ctx.run_step("entity-resolution", 3, summary)
        return _lookup_success(ctx, entities=entities, summary=summary)

    if intent in {"list", "aggregate", "trend", "forecast"}:
        entities["org"] = _normalize_org(entities.get("org"), question)
        org = entities["org"]
        if intent == "list":
            list_filters = extract_list_filters(question)
            if list_filters:
                entities["list_filters"] = list_filters
            entities["target_l3"] = ["l3-2-1-4"]
            scope = org.get("部门") or org.get("事业部") or "全公司"
            filt = f" · 筛选 {list_filters}" if list_filters else ""
            summary = f"清单范围：{scope}{filt}"
        elif intent == "aggregate":
            if "离职率" in question or ("离职" in question and "率" in question):
                entities["target_l3"] = ["l3-2-5-1"]
            else:
                entities["target_l3"] = ["l3-2-2-1"] if "假" in question else ["l3-2-2-4"] if "加班" in question else ["l3-2-2-1"]
            summary = f"聚合范围：{org.get('事业部') or '全部事业部'} / {org.get('统计月份') or '2025-10'}"
        elif intent == "trend":
            entities["target_l3"] = ["l3-2-5-1"]
            topic = "离职率" if "离职" in question else "指标"
            entities["topic"] = topic
            summary = f"趋势范围：{org.get('事业部') or org.get('部门') or '全公司'} / {topic}"
        else:
            entities["target_l3"] = ["l3-6-1-1"]
            summary = f"预测范围：{org.get('事业部') or org.get('部门') or '全公司'}"
        if entities.get("metric"):
            summary += f" · 指标 {entities['metric']['name']}"
        ctx.run_step("entity-resolution", 2, f"校验范围（{source}）")
        ctx.run_step("entity-resolution", 3, summary)
        return _lookup_success(ctx, entities=entities, summary=summary)

    if intent != "lookup":
        ctx.run_step("entity-resolution", 3, "本意图无需员工解析")
        return _lookup_success(ctx, entities=entities, summary="本意图无需员工解析")

    return await _finalize_lookup(db, state, ctx, entities)


async def _finalize_lookup(
    db: AsyncSession,
    state: AgentState,
    ctx,
    entities: dict[str, Any],
) -> dict[str, Any]:
    question = state.get("question") or ""
    context_q = effective_lookup_question(state)
    employee = entities.get("employee") or {}

    if is_org_metric_question(question):
        entities = dict(entities)
        entities["org"] = _normalize_org(entities.get("org"), question)
        if "离职" in question:
            entities["target_l3"] = ["l3-2-5-1"]
        org = entities["org"]
        summary = f"聚合范围：{org.get('事业部') or '全部事业部'} / {org.get('统计月份') or '2025-10'}"
        ctx.run_step("entity-resolution", 2, "组织指标问法误入 lookup，按组织范围校验")
        ctx.run_step("entity-resolution", 3, summary)
        return _lookup_success(ctx, entities=entities, summary=summary)

    if employee.get("工号"):
        if entities.get("lookup_scope"):
            scope = str(entities["lookup_scope"])
            entities["target_l3"] = lookup_target_l3s(scope)
            name = employee.get("姓名") or "员工"
            summary = f"{name} → {employee.get('工号')} · 查询范围 {scope}"
            ctx.run_step("entity-resolution", 3, summary)
            return _lookup_success(ctx, entities=entities, summary=summary)
        if is_vague_lookup_question(context_q):
            name = employee.get("姓名") or "该员工"
            return _lookup_clarify(
                ctx,
                clarify=build_scope_clarify(name),
                entities=entities,
                summary=f"需澄清查询范围：{name}",
            )
        entities["target_l3"] = lookup_target_l3s(None)
        summary = f"{employee.get('姓名')} → 工号 {employee.get('工号')} / {employee.get('部门')}"
        ctx.run_step("entity-resolution", 3, summary)
        return _lookup_success(ctx, entities=entities, summary=summary)

    match = _NAME_RE.search(context_q) or _NAME_RE.search(question)
    if not match:
        return _lookup_clarify(
            ctx,
            clarify={"kind": "employee", "question": "请问您要查询哪位员工？", "options": []},
            entities=entities,
            summary="未识别到员工姓名",
        )

    name = match.group(0)
    ctx.run_step("entity-resolution", 2, f"查花名册匹配：{name}")
    result = await _resolve_employee_name(db, ctx, entities, name)
    if result.get("clarify"):
        return result
    entities = result.get("entities") or entities

    if is_vague_lookup_question(context_q):
        return _lookup_clarify(
            ctx,
            clarify=build_scope_clarify(name),
            entities=entities,
            summary=f"需澄清查询范围：{name}",
        )

    entities["target_l3"] = lookup_target_l3s(None)
    emp = entities.get("employee") or {}
    summary = f"{name} → 工号 {emp.get('工号')} / {emp.get('部门')}"
    ctx.run_step("entity-resolution", 3, summary)
    return _lookup_success(ctx, entities=entities, summary=summary)
