from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.planner_rules import filter_roster_rows
from src.agent.skills.runner import begin_agent_run
from src.agent.state import AgentState
from src.agent.tools.registry import call_tool


def compose_answer(state: AgentState, *, rag_draft: str | None = None) -> dict[str, Any]:
    ctx = begin_agent_run("Composer", state, subtask_type="compose")
    ctx.run_step("answer-composition", 1, "组织答案结构")

    if state.get("rejected"):
        return {**ctx.to_state_patch(), "final": state.get("reject_reason") or "无法回答。"}

    clarify = state.get("clarify")
    if clarify:
        return {**ctx.to_state_patch(), "final": clarify.get("question") or "需要补充信息。"}

    intent = state.get("intent")
    if intent == "policy":
        return _compose_policy(state, ctx, rag_draft=rag_draft)
    if intent == "lookup":
        return _compose_lookup(state, ctx)
    if intent == "compare":
        return _compose_compare(state, ctx)
    if intent == "attribution":
        return _compose_attribution(state, ctx)
    if intent == "list":
        return _compose_list(state, ctx)
    if intent == "aggregate":
        return _compose_aggregate(state, ctx)
    if intent == "trend":
        return _compose_trend(state, ctx)
    if intent == "forecast":
        return _compose_forecast(state, ctx)
    trace = [ctx.trace_entry(subtask_id="composer", summary="未支持")]
    return {**ctx.to_state_patch(), "final": f"意图「{intent}」暂未支持。", "trace": trace}


def _render_charts(ctx, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not specs:
        return []
    ctx.run_step("data-visualization", 1, "按 chart spec 触发 chart_render")
    rendered: list[dict[str, Any]] = []
    for spec in specs:
        ctx.record_tool("chart_render")
        rendered.append(call_tool("chart_render", spec=spec))
    ctx.run_step("data-visualization", 2, "渲染完成")
    return rendered


def _compose_policy(state: AgentState, ctx, *, rag_draft: str | None = None) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for block in state.get("evidence") or []:
        if block.get("kind") == "documents":
            hits.extend(block.get("hits") or [])

    if not hits:
        final = "未在现行制度文档中找到相关规定，无法回答。请尝试换个说法或上传相关制度文档。"
        trace = [ctx.trace_entry(subtask_id="composer", summary="无命中，不臆造")]
        return {**ctx.to_state_patch(), "final": final, "citations": [], "trace": trace}

    ctx.run_step("document-rag", 3, "rag_answer 生成制度草稿" if rag_draft else "模板组织制度答案")
    ctx.run_step("answer-composition", 2, "标注条文出处")
    if rag_draft:
        final = rag_draft.strip()
    else:
        lines = [f"- {str(hit.get('text') or '')[:280]}" for hit in hits[:3]]
        source = hits[0].get("title_path") or "员工手册"
        if isinstance(source, list):
            source = source[-1] if source else "员工手册"
        final = "根据现行制度文档：\n" + "\n".join(lines) + f"\n\n出处：{source}"
    citations = [
        {
            "kind": "doc",
            "l3_id": block.get("l3_id") or "l3-1-1-1",
            "doc_id": hit.get("doc_id") or hit.get("document_id"),
            "seq": hit.get("seq"),
            "title_path": hit.get("title_path"),
            "chunk": hit.get("text"),
            "score": hit.get("score"),
        }
        for block in state.get("evidence") or []
        if block.get("kind") == "documents"
        for hit in (block.get("hits") or [])[:5]
    ]
    trace = [ctx.trace_entry(subtask_id="composer", summary="已组织制度答案")]
    return {**ctx.to_state_patch(), "final": final, "citations": citations, "trace": trace}


def _compose_lookup(state: AgentState, ctx) -> dict[str, Any]:
    employee = (state.get("entities") or {}).get("employee") or {}
    name = employee.get("姓名") or "该员工"
    emp_no = employee.get("工号") or "—"
    scope = (state.get("entities") or {}).get("lookup_scope")
    perf_rows: list[dict[str, Any]] = []
    leave_rows: list[dict[str, Any]] = []
    overtime_rows: list[dict[str, Any]] = []
    for block in state.get("evidence") or []:
        if block.get("kind") != "structured":
            continue
        l3_id = block.get("l3_id")
        block_rows = block.get("rows") or []
        if l3_id == "l3-5-1-1":
            perf_rows.extend(block_rows)
        elif l3_id == "l3-2-2-1":
            leave_rows.extend(block_rows)
        elif l3_id == "l3-2-2-4":
            overtime_rows.extend(block_rows)
        elif block_rows and block_rows[0].get("绩效得分") is not None:
            perf_rows.extend(block_rows)
        else:
            leave_rows.extend(block_rows)

    rows = perf_rows or leave_rows or overtime_rows
    if scope == "overview" or (perf_rows and (leave_rows or overtime_rows)):
        sections: list[str] = []
        if perf_rows:
            perf_lines = [
                f"- {row.get('考核周期') or '—'}：得分 {row.get('绩效得分')}，等级 {row.get('绩效等级')}（部门排名 {row.get('部门排名') or '—'}）"
                for row in perf_rows[:3]
            ]
            sections.append("【绩效】\n" + "\n".join(perf_lines))
        if leave_rows:
            leave_lines = [
                f"- {row.get('请假类型')}：{row.get('开始日期')} ~ {row.get('结束日期')}（{row.get('请假天数')} 天）"
                for row in leave_rows[:3]
            ]
            sections.append("【请假】\n" + "\n".join(leave_lines))
        if overtime_rows:
            ot_total = sum(float(row.get("加班时长") or 0) for row in overtime_rows)
            sections.append(f"【加班】近期间合计 {ot_total:.1f} 小时（{len(overtime_rows)} 条记录）")
        if sections:
            ctx.run_step("answer-composition", 2, "组织综合近况")
            final = f"{name}（工号 {emp_no}）近期情况：\n\n" + "\n\n".join(sections)
            trace = [ctx.trace_entry(subtask_id="composer", summary="已组织综合近况")]
            return {**ctx.to_state_patch(), "final": final, "trace": trace}

    topic = "业务数据"
    if perf_rows or (rows and rows[0].get("绩效得分") is not None):
        topic = "绩效记录"
        rows = perf_rows or rows
    elif leave_rows or "假" in (state.get("question") or ""):
        topic = "请假记录"
        rows = leave_rows or rows
    elif overtime_rows or scope == "attendance":
        topic = "加班记录"
        rows = overtime_rows or rows

    if not rows:
        final = f"未查询到 {name}（工号 {emp_no}）的相关{topic}。"
        trace = [ctx.trace_entry(subtask_id="composer", summary="无数据")]
        return {**ctx.to_state_patch(), "final": final, "trace": trace}

    ctx.run_step("answer-composition", 2, "附结构化 locator")
    if topic == "绩效记录":
        detail_lines = [
            f"- {row.get('考核周期') or '—'}：得分 {row.get('绩效得分')}，等级 {row.get('绩效等级')}（部门排名 {row.get('部门排名') or '—'}）"
            for row in rows[:5]
        ]
        final = f"{name}（工号 {emp_no}）近期绩效如下：\n" + "\n".join(detail_lines)
    elif topic == "加班记录":
        ot_total = sum(float(row.get("加班时长") or 0) for row in rows)
        detail_lines = [
            f"- {row.get('加班日期')}：{row.get('加班时长')} 小时（{row.get('审批状态') or '—'}）"
            for row in rows[:5]
        ]
        final = f"{name}（工号 {emp_no}）加班合计 {ot_total:.1f} 小时：\n" + "\n".join(detail_lines)
    else:
        total_days = sum(int(row.get("请假天数") or 0) for row in rows)
        detail_lines = [
            f"- {row.get('请假类型')}：{row.get('开始日期')} ~ {row.get('结束日期')}（{row.get('请假天数')} 天，{row.get('审批状态') or '—'}）"
            for row in rows[:5]
        ]
        final = f"{name}（工号 {emp_no}）共 {len(rows)} 条请假记录，合计 {total_days} 天：\n" + "\n".join(detail_lines)
    trace = [ctx.trace_entry(subtask_id="composer", summary="已组织结构化答案")]
    return {**ctx.to_state_patch(), "final": final, "trace": trace}


def _compose_compare(state: AgentState, ctx) -> dict[str, Any]:
    analysis = state.get("analysis") or {}
    limitation = state.get("limitation") or ""
    if not analysis.get("sufficient"):
        final = f"无法完成对比分析：{analysis.get('reason') or state.get('critic_note') or '数据不足'}"
        trace = [ctx.trace_entry(subtask_id="composer", summary="对比失败")]
        return {**ctx.to_state_patch(), "final": final, "trace": trace}

    lines = analysis.get("summary_lines") or []
    final = f"结论：{analysis.get('conclusion')}\n\n" + "\n".join(lines)
    final += f"\n\n口径：{analysis.get('citation') or '人均人力成本 = 部门人力成本合计 / 在职人数'}"
    if limitation:
        final += f"\n\n说明：{limitation}"

    charts = _render_charts(ctx, state.get("charts") or [])
    ctx.run_step("answer-composition", 3, "输出对比结论与图表")
    trace = [ctx.trace_entry(subtask_id="composer", summary="已输出对比结论与图表")]
    return {**ctx.to_state_patch(), "final": final, "charts": charts, "trace": trace}


def _compose_attribution(state: AgentState, ctx) -> dict[str, Any]:
    analysis = state.get("analysis") or {}
    factors = analysis.get("factors") or []
    limitation = state.get("limitation") or ""
    if analysis.get("conclusion") and analysis.get("risk_list"):
        final = f"结论：{analysis.get('conclusion')}\n\n"
        final += "\n".join(f"- {x}" for x in factors)
        final += f"\n\n{analysis.get('citation') or ''}"
        if limitation:
            final += f"\n\n说明：{limitation}"
        trace = [ctx.trace_entry(subtask_id="composer", summary="已组织离职风险结论")]
        return {**ctx.to_state_patch(), "final": final, "trace": trace}
    if not factors:
        final = "现有数据不足以完成归因分析，请补充组织范围或时间周期后重试。"
        trace = [ctx.trace_entry(subtask_id="composer", summary="归因证据不足")]
        return {**ctx.to_state_patch(), "final": final, "trace": trace}

    final = "可能影响因素：\n" + "\n".join(f"- {x}" for x in factors)
    final += f"\n\n口径：{analysis.get('citation')}"
    if limitation:
        final += f"\n\n说明：{limitation}"
    trace = [ctx.trace_entry(subtask_id="composer", summary="已组织归因结论")]
    return {**ctx.to_state_patch(), "final": final, "trace": trace}


def _compose_list(state: AgentState, ctx) -> dict[str, Any]:
    entities = state.get("entities") or {}
    org = entities.get("org") or {}
    scope = org.get("部门") or org.get("事业部") or "全公司"
    list_filters = entities.get("list_filters") or {}

    rows: list[dict[str, Any]] = []
    for block in state.get("evidence") or []:
        if block.get("kind") == "structured" and block.get("l3_id") == "l3-2-1-4":
            rows.extend(block.get("rows") or [])
    rows = filter_roster_rows(rows, list_filters)

    if not rows:
        final = f"未找到 {scope} 符合条件的员工名单。"
        trace = [ctx.trace_entry(subtask_id="composer", summary="清单为空")]
        return {**ctx.to_state_patch(), "final": final, "trace": trace}

    lines = [
        f"- {row.get('姓名')}（{row.get('工号')}）· {row.get('部门')} · {row.get('序列') or row.get('职务')}"
        for row in rows[:30]
    ]
    filt_note = f"（筛选：{list_filters}）" if list_filters else ""
    final = f"{scope} 员工名单{filt_note}，共 {len(rows)} 人：\n" + "\n".join(lines)
    if len(rows) > 30:
        final += f"\n\n… 其余 {len(rows) - 30} 人未展示"
    trace = [ctx.trace_entry(subtask_id="composer", summary=f"输出 {len(rows)} 人名单")]
    return {**ctx.to_state_patch(), "final": final, "trace": trace}


def _compose_aggregate(state: AgentState, ctx) -> dict[str, Any]:
    entities = state.get("entities") or {}
    org = entities.get("org") or {}
    month = org.get("统计月份") or "2025-10"

    rows: list[dict[str, Any]] = []
    group_by: list[str] = []
    for block in state.get("evidence") or []:
        if block.get("kind") != "structured":
            continue
        rows.extend(block.get("rows") or [])
        group_by = block.get("group_by") or group_by
        if block.get("agg") and not rows:
            rows = [block["agg"]]

    if not rows:
        final = f"未查询到 {month} 的聚合结果。"
        trace = [ctx.trace_entry(subtask_id="composer", summary="聚合无数据")]
        return {**ctx.to_state_patch(), "final": final, "trace": trace}

    if rows and "离职率" in rows[0]:
        scope = org.get("事业部") or org.get("部门") or rows[0].get("事业部") or "目标组织"
        lines = []
        total_staff = 0
        total_left = 0
        for row in rows[:20]:
            dept = row.get("部门") or "—"
            staff = int(row.get("在职人数") or 0)
            left = int(row.get("离职人数") or 0)
            total_staff += staff
            total_left += left
            rate = row.get("离职率")
            rate_txt = f"{float(rate) * 100:.1f}%" if rate is not None else "—"
            lines.append(f"- {dept}：离职率 {rate_txt}（在职 {staff} 人，离职 {left} 人）")
        headline = f"{scope} {month} 离职率"
        if total_staff and len(rows) > 1:
            headline += f"（整体约 {total_left / total_staff * 100:.1f}%）"
        final = headline + "：\n" + "\n".join(lines)
        trace = [ctx.trace_entry(subtask_id="composer", summary=f"离职率 {len(rows)} 组")]
        return {**ctx.to_state_patch(), "final": final, "trace": trace}

    lines = []
    for row in rows[:20]:
        if group_by:
            label = " / ".join(str(row.get(k) or "—") for k in group_by)
            metric_keys = [k for k in row if k not in group_by]
            metric_txt = "，".join(f"{k}={row[k]}" for k in metric_keys if row.get(k) is not None)
            lines.append(f"- {label}：{metric_txt}")
        else:
            lines.append("- " + "，".join(f"{k}={v}" for k, v in row.items()))

    metric = (entities.get("metric") or {}).get("name") or "汇总指标"
    final = f"{month} 聚合结果（{metric}）：\n" + "\n".join(lines)
    trace = [ctx.trace_entry(subtask_id="composer", summary=f"聚合 {len(rows)} 组")]
    return {**ctx.to_state_patch(), "final": final, "trace": trace}


def _compose_trend(state: AgentState, ctx) -> dict[str, Any]:
    analysis = state.get("analysis") or {}
    limitation = state.get("limitation") or ""
    if not analysis.get("sufficient"):
        final = f"无法完成趋势分析：{analysis.get('reason') or '数据不足'}"
        trace = [ctx.trace_entry(subtask_id="composer", summary="趋势失败")]
        return {**ctx.to_state_patch(), "final": final, "trace": trace}

    lines = analysis.get("summary_lines") or []
    final = f"结论：{analysis.get('conclusion')}\n\n" + "\n".join(lines)
    final += f"\n\n口径：{analysis.get('citation') or ''}"
    if limitation:
        final += f"\n\n说明：{limitation}"
    charts = _render_charts(ctx, state.get("charts") or [])
    trace = [ctx.trace_entry(subtask_id="composer", summary="已输出趋势结论")]
    return {**ctx.to_state_patch(), "final": final, "charts": charts, "trace": trace}


def _compose_forecast(state: AgentState, ctx) -> dict[str, Any]:
    analysis = state.get("analysis") or {}
    if not analysis.get("sufficient") and not analysis.get("summary_lines"):
        final = f"无法完成预测：{analysis.get('reason') or '数据不足'}"
        trace = [ctx.trace_entry(subtask_id="composer", summary="预测失败")]
        return {**ctx.to_state_patch(), "final": final, "trace": trace}

    lines = analysis.get("summary_lines") or []
    final = f"结论：{analysis.get('conclusion')}\n\n" + "\n".join(f"- {x}" for x in lines)
    final += f"\n\n口径：{analysis.get('citation') or ''}"
    final += "\n\n说明：基于当前编制与在岗人数的静态估算，非确定预测。"
    trace = [ctx.trace_entry(subtask_id="composer", summary="已输出预测结论")]
    return {**ctx.to_state_patch(), "final": final, "trace": trace}


# Legacy helper kept for imports elsewhere
async def retrieve_documents(db: AsyncSession, state: AgentState) -> dict[str, Any]:
    from src.agent.supervisor import HANDBOOK_L3, execute_retrieve_subtask

    subtask = {"type": "retrieve", "retrieve_mode": "rag", "target_l3": [HANDBOOK_L3], "id": "document"}
    return await execute_retrieve_subtask(db, state, subtask)
