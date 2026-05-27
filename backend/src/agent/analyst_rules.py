from __future__ import annotations

from typing import Any

from src.agent.skills.runner import SkillRunContext, begin_agent_run
from src.agent.state import AgentState
from src.agent.tools.registry import call_tool


def _rows(state: AgentState, l3_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in state.get("evidence") or []:
        if block.get("kind") == "structured" and block.get("l3_id") == l3_id:
            rows.extend(block.get("rows") or [])
    return rows


def run_analyst_rules(state: AgentState) -> dict[str, Any]:
    ctx = begin_agent_run("Analyst", state, subtask_type="analyze")
    intent = state.get("intent")
    question = state.get("question") or ""
    if "离职风险" in question or ("风险" in question and "离职" in question):
        return _analyze_turnover_risk(state, ctx)
    if intent == "compare":
        return _analyze_compare(state, ctx)
    if intent == "attribution":
        return _analyze_attribution(state, ctx)
    if intent == "trend":
        return _analyze_trend(state, ctx)
    if intent == "forecast":
        return _analyze_forecast(state, ctx)
    trace = [ctx.trace_entry(subtask_id="analyst", summary="跳过分析")]
    return {**ctx.to_state_patch(), "trace": trace}


def _entity_metric(state: AgentState, default_name: str) -> dict[str, Any]:
    metric = (state.get("entities") or {}).get("metric")
    if isinstance(metric, dict) and metric.get("name"):
        return dict(metric)
    return {"name": default_name}


def _metric_citation(
    ctx: SkillRunContext,
    metric_name: str,
    inputs: dict[str, Any],
    *,
    metric_spec: dict[str, Any] | None = None,
) -> str:
    if metric_spec and metric_spec.get("citation"):
        ctx.run_step("metric-dictionary", 2, f"沿用 Resolver 口径：{metric_spec.get('name')}")
        ctx.run_step("metric-dictionary", 3, "引用标准 citation")
        return str(metric_spec["citation"])
    ctx.run_step("metric-dictionary", 2, f"查口径：{metric_name}")
    ctx.record_tool("calc")
    try:
        result = call_tool("calc", metric=metric_name, inputs=inputs)
        ctx.run_step("metric-dictionary", 3, "引用标准 citation")
        return str(result.get("citation") or result.get("formula") or metric_name)
    except (ValueError, KeyError):
        return metric_name


def _dept_peer_mean(perf_rows: list[dict[str, Any]], row: dict[str, Any]) -> float | None:
    dept = row.get("部门")
    period = row.get("考核周期")
    peers = [
        r for r in perf_rows
        if r.get("部门") == dept and r.get("考核周期") == period and r.get("绩效得分") is not None
    ]
    if len(peers) < 2:
        return None
    scores = [float(r.get("绩效得分") or 0) for r in peers]
    return sum(scores) / len(scores)


def _analyze_compare(state: AgentState, ctx: SkillRunContext) -> dict[str, Any]:
    ctx.run_step("compare-benchmark", 1, "识别对比维度：事业部人均成本")
    ctx.run_step("process-headcount-planning", 1, "加载编制/成本流程 skill")

    cost_rows = _rows(state, "l3-4-6-3")
    if not cost_rows:
        trace = [ctx.trace_entry(subtask_id="analyst", summary="无成本数据")]
        return {
            **ctx.to_state_patch(),
            "analysis": {"sufficient": False, "reason": "缺少事业部成本数据"},
            "trace": trace,
        }

    ctx.run_step("compare-benchmark", 2, "排序并计算偏离度")
    ranked = sorted(cost_rows, key=lambda r: float(r.get("人均成本") or 0), reverse=True)
    top = ranked[0]
    metric_spec = _entity_metric(state, "人均人力成本")
    metric_name = str(metric_spec.get("name") or "人均人力成本")
    citation = _metric_citation(
        ctx,
        metric_name,
        {
            "部门人力成本合计": float(top.get("人均成本") or 0) * max(int(top.get("人数") or 1), 1),
            "在职人数": max(int(top.get("人数") or 1), 1),
        },
        metric_spec=metric_spec,
    )

    lines = []
    chart_data = []
    for row in ranked:
        bu = row.get("事业部")
        value = float(row.get("人均成本") or 0)
        lines.append(f"- {bu}：{value:.2f} 万/人/月（人数 {row.get('人数')}）")
        chart_data.append({"name": bu, "value": value})

    ctx.run_step("compare-benchmark", 3, "引用指标口径字典")
    analysis = {
        "sufficient": True,
        "conclusion": f"人均成本最高的是 {top.get('事业部')}（{float(top.get('人均成本') or 0):.2f} 万/人/月）",
        "summary_lines": lines,
        "citation": citation,
        "metric": metric_spec,
        "ranked": ranked,
    }
    charts = [
        {
            "type": "bar",
            "title": "各事业部人均成本（万/人/月）",
            "x_field": "name",
            "y_field": "value",
            "data": chart_data,
        }
    ]
    trace = [ctx.trace_entry(subtask_id="analyst", summary=f"完成 {len(ranked)} 个事业部对比")]
    return {**ctx.to_state_patch(), "analysis": analysis, "charts": charts, "trace": trace}


def _analyze_attribution(state: AgentState, ctx: SkillRunContext) -> dict[str, Any]:
    entities = state.get("entities") or {}
    topic = entities.get("topic") or "综合"
    employee = entities.get("employee") or {}
    if topic == "离职":
        ctx.run_step("process-resignation-attribution", 1, "解析组织范围与归因主题")
    elif topic == "绩效":
        ctx.run_step("process-performance-diagnosis", 1, "加载个人绩效诊断 skill")
    ctx.run_step("attribution-methodology", 1, "归纳影响因素")

    turnover_rows = _rows(state, "l3-2-5-1")
    change_rows = _rows(state, "l3-2-3-1")
    all_perf_rows = _rows(state, "l3-5-1-1")
    perf_rows = all_perf_rows

    emp_id = str(employee.get("工号") or "")
    if emp_id:
        change_rows = [r for r in change_rows if str(r.get("工号") or "") == emp_id]
        perf_rows = [r for r in all_perf_rows if str(r.get("工号") or "") == emp_id]

    default_metric = "离职率" if topic == "离职" else "绩效分布偏离" if topic == "绩效" else "离职率"
    metric_spec = _entity_metric(state, default_metric)
    metric_name = str(metric_spec.get("name") or default_metric)

    factors: list[str] = []
    citation_inputs = {
        "期间离职人数": int((turnover_rows[0] if turnover_rows else {}).get("离职人数") or 1),
        "期间平均在职人数": max(int((turnover_rows[0] if turnover_rows else {}).get("在职人数") or 1), 1),
    }
    if metric_name == "绩效分布偏离" and perf_rows:
        target_rows = perf_rows
        if employee.get("工号"):
            target_rows = [r for r in perf_rows if str(r.get("工号") or "") == str(employee["工号"])] or perf_rows
        row = target_rows[0]
        peer_mean = _dept_peer_mean(all_perf_rows, row)
        if peer_mean is not None:
            citation_inputs = {
                "个体得分": float(row.get("绩效得分") or 0),
                "同部门同岗均值": peer_mean,
            }
    citation = _metric_citation(ctx, metric_name, citation_inputs, metric_spec=metric_spec)

    if topic == "离职" or turnover_rows:
        ctx.record_tool("calc")
        for row in turnover_rows[:3]:
            quit_n = int(row.get("离职人数") or 0)
            active_n = max(int(row.get("在职人数") or 0), 1)
            calc = call_tool(
                "calc",
                metric="离职率",
                inputs={"期间离职人数": quit_n, "期间平均在职人数": active_n},
            )
            factors.append(
                f"{row.get('部门')} 离职率 {calc.get('formatted') or calc.get('value')}（在职 {active_n}，离职 {quit_n}）"
            )
        for row in change_rows:
            if str(row.get("异动类型") or "") == "离职":
                factors.append(
                    f"近期离职：{row.get('姓名')}（{row.get('原部门')}，原因：{row.get('异动原因')}）"
                )
    if topic == "绩效" or perf_rows:
        target_rows = perf_rows
        if employee.get("工号"):
            target_rows = [r for r in perf_rows if str(r.get("工号") or "") == str(employee["工号"])] or perf_rows
        for row in target_rows[:3]:
            line = (
                f"{row.get('姓名')} {row.get('考核周期')} 绩效 {row.get('绩效得分')}"
                f"（{row.get('绩效等级')}，部门排名 {row.get('部门排名')}）"
            )
            if metric_name == "绩效分布偏离":
                peer_mean = _dept_peer_mean(all_perf_rows, row)
                if peer_mean is not None:
                    try:
                        calc = call_tool(
                            "calc",
                            metric=metric_name,
                            inputs={
                                "个体得分": float(row.get("绩效得分") or 0),
                                "同部门同岗均值": peer_mean,
                            },
                        )
                        threshold = metric_spec.get("threshold") or "低于同部门同岗均值"
                        line += f"；{metric_name} {calc.get('formatted') or calc.get('value')}（基准 {metric_spec.get('benchmark') or '同部门同岗均值'}，阈值 {threshold}）"
                    except (ValueError, KeyError):
                        pass
            factors.append(line)

    if employee and not perf_rows and topic == "绩效":
        factors.append(f"未找到 {employee.get('姓名')} 的绩效记录，无法完成个人绩效诊断。")

    ctx.run_step("attribution-methodology", 3, "按贡献度排序并标注口径")
    sufficient = len(factors) > 0
    analysis = {
        "sufficient": sufficient,
        "topic": topic,
        "factors": factors,
        "employee": employee,
        "metric": metric_spec,
        "citation": citation,
    }
    trace = [
        ctx.trace_entry(
            subtask_id="analyst",
            summary=f"归纳 {len(factors)} 条因子" if sufficient else "证据不足",
        )
    ]
    return {**ctx.to_state_patch(), "analysis": analysis, "trace": trace}


def _analyze_turnover_risk(state: AgentState, ctx: SkillRunContext) -> dict[str, Any]:
    ctx.run_step("process-turnover-risk-alert", 1, "离职风险加权识别")
    perf_rows = _rows(state, "l3-5-1-1")
    overtime_rows = _rows(state, "l3-2-2-4")
    change_rows = _rows(state, "l3-2-3-1")

    risks: list[dict[str, Any]] = []
    perf_by_id = {str(r.get("工号")): r for r in perf_rows if r.get("工号")}
    ot_by_id: dict[str, float] = {}
    for row in overtime_rows:
        eid = str(row.get("工号") or "")
        if eid:
            ot_by_id[eid] = ot_by_id.get(eid, 0.0) + float(row.get("加班时长") or 0)

    for eid, perf in perf_by_id.items():
        score = float(perf.get("绩效得分") or 0)
        reasons: list[str] = []
        risk_score = 0.0
        if score < 70:
            reasons.append("绩效偏低")
            risk_score += 0.4
        ot_hours = ot_by_id.get(eid, 0)
        if ot_hours > 60:
            reasons.append("加班畸高")
            risk_score += 0.35
        elif ot_hours < 5:
            reasons.append("加班畸低")
            risk_score += 0.15
        for ch in change_rows:
            if str(ch.get("工号") or "") == eid and "晋升" not in str(ch.get("异动类型") or ""):
                reasons.append("近期异动")
                risk_score += 0.1
                break
        if risk_score >= 0.4 and reasons:
            risks.append(
                {
                    "工号": eid,
                    "姓名": perf.get("姓名"),
                    "risk_score": round(risk_score, 2),
                    "主因": "、".join(reasons[:2]),
                }
            )

    risks.sort(key=lambda x: x["risk_score"], reverse=True)
    factors = [f"{r['姓名']}({r['工号']}) 风险{r['risk_score']} 主因:{r['主因']}" for r in risks[:5]]
    ctx.run_step("process-turnover-risk-alert", 2, f"识别 {len(risks)} 人高风险")
    analysis = {
        "sufficient": len(risks) > 0,
        "conclusion": f"识别 {len(risks)} 名员工存在较高离职风险（风险提示非确定）。",
        "factors": factors,
        "risk_list": risks[:10],
        "citation": "风险加权=绩效趋势+加班异常+近期异动（风险提示非确定）",
    }
    trace = [ctx.trace_entry(subtask_id="analyst", summary=f"离职风险 {len(risks)} 人")]
    return {**ctx.to_state_patch(), "analysis": analysis, "trace": trace}


def _analyze_trend(state: AgentState, ctx: SkillRunContext) -> dict[str, Any]:
    ctx.run_step("trend-analysis", 1, "加载趋势分析 skill")
    entities = state.get("entities") or {}
    topic = entities.get("topic") or ("离职率" if "离职" in (state.get("question") or "") else "指标")
    metric_spec = _entity_metric(state, "离职率" if topic == "离职率" else topic)

    rows = _rows(state, "l3-2-5-1")
    if not rows:
        trace = [ctx.trace_entry(subtask_id="analyst", summary="无趋势数据")]
        return {**ctx.to_state_patch(), "analysis": {"sufficient": False, "reason": "缺少多期指标数据"}, "trace": trace}

    field = "离职率" if topic == "离职率" else next((k for k in rows[0] if k.endswith("率")), "离职率")
    sorted_rows = sorted(rows, key=lambda r: str(r.get("统计周期") or ""))
    points = []
    lines = []
    for row in sorted_rows:
        period = str(row.get("统计周期") or "—")
        value = float(row.get(field) or 0)
        label = f"{row.get('部门') or row.get('事业部') or ''} {period}".strip()
        points.append({"x": period, "y": round(value * 100 if value <= 1 else value, 2), "name": label})
        lines.append(f"- {label}：{value * 100 if value <= 1 else value:.2f}{'%' if field.endswith('率') else ''}")

    ctx.run_step("trend-analysis", 2, f"识别 {len(points)} 个时间点")
    citation = _metric_citation(ctx, str(metric_spec.get("name") or field), {}, metric_spec=metric_spec)
    charts = [
        {
            "type": "line",
            "title": f"{topic}走势",
            "x_field": "x",
            "y_field": "y",
            "data": points,
        }
    ]
    analysis = {
        "sufficient": len(points) >= 2,
        "conclusion": f"{topic}共 {len(points)} 个统计周期，详见趋势图。",
        "summary_lines": lines,
        "metric": metric_spec,
        "citation": citation,
    }
    trace = [ctx.trace_entry(subtask_id="analyst", summary=f"趋势 {len(points)} 点")]
    return {**ctx.to_state_patch(), "analysis": analysis, "charts": charts, "trace": trace}


def _analyze_forecast(state: AgentState, ctx: SkillRunContext) -> dict[str, Any]:
    ctx.run_step("process-headcount-planning", 1, "编制缺口估算")
    rows = _rows(state, "l3-6-1-1")
    if not rows:
        trace = [ctx.trace_entry(subtask_id="analyst", summary="无编制数据")]
        return {**ctx.to_state_patch(), "analysis": {"sufficient": False, "reason": "缺少编制数据"}, "trace": trace}

    gaps: list[str] = []
    total_gap = 0
    for row in rows:
        quota = int(row.get("编制数") or 0)
        actual = int(row.get("实有人数") or 0)
        gap = quota - actual
        total_gap += gap
        if gap > 0:
            gaps.append(f"{row.get('部门') or row.get('岗位')}：缺口 {gap}（编制 {quota} / 在岗 {actual}）")

    ctx.run_step("process-headcount-planning", 2, f"识别 {len(gaps)} 个缺口岗位")
    analysis = {
        "sufficient": len(gaps) > 0 or total_gap != 0,
        "conclusion": f"预计编制缺口合计 {total_gap} 人（基于当前在岗与编制，非确定预测）。",
        "summary_lines": gaps or ["当前无明显编制缺口。"],
        "citation": "编制缺口 = 编制数 − 实有人数（风险提示非确定）",
    }
    trace = [ctx.trace_entry(subtask_id="analyst", summary=f"缺口 {total_gap} 人")]
    return {**ctx.to_state_patch(), "analysis": analysis, "trace": trace}
