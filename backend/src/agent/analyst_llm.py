"""Analyst LLM wrapper — rules fallback."""

from __future__ import annotations

from typing import Any

from src.agent.analyst_rules import run_analyst_rules
from src.agent.llm_runner import agent_llm_enabled, llm_json
from src.agent.prompts import ANALYST_SYSTEM
from src.agent.skills.runner import begin_agent_run
from src.agent.state import AgentState


def run_analyst(state: AgentState) -> dict[str, Any]:
    intent = state.get("intent")
    if agent_llm_enabled():
        llm_result = _run_analyst_llm(state)
        if llm_result is not None:
            if intent == "compare" and not llm_result.get("charts"):
                rules = run_analyst_rules(state)
                llm_result["charts"] = rules.get("charts") or []
                analysis = dict(llm_result.get("analysis") or {})
                rules_analysis = rules.get("analysis") or {}
                for key in ("summary_lines", "ranked", "conclusion", "citation", "metric"):
                    if not analysis.get(key) and rules_analysis.get(key):
                        analysis[key] = rules_analysis[key]
                if rules_analysis.get("sufficient") is not False:
                    analysis["sufficient"] = True
                llm_result["analysis"] = analysis
            return llm_result
    return run_analyst_rules(state)


def _run_analyst_llm(state: AgentState) -> dict[str, Any] | None:
    ctx = begin_agent_run("Analyst", state, subtask_type="analyze")
    ctx.run_step("compare-benchmark", 1, "LLM 分析")

    evidence_preview = _evidence_preview(state)
    metric = (state.get("entities") or {}).get("metric") or {}
    user = (
        f"question={state.get('question')}\n"
        f"intent={state.get('intent')}\n"
        f"entities={state.get('entities')}\n"
        f"resolved_metric={metric}\n"
        f"evidence_summary={evidence_preview}\n"
        "只输出 JSON：{\"findings\":[],\"metrics_used\":[],\"factors\":[],\"series\":[],\"need_more\":[],\"sufficient\":true,\"conclusion\":\"\"}"
    )
    payload = llm_json(
        agent="Analyst",
        system=ANALYST_SYSTEM,
        user=user,
        state=state,
        subtask_type="analyze",
        max_tokens=1500,
    )
    if not payload:
        return None

    findings = payload.get("findings") or []
    factors_raw = payload.get("factors") or []
    series = payload.get("series") or []
    metrics_used = payload.get("metrics_used") or []
    sufficient = bool(payload.get("sufficient", len(findings) > 0 or len(factors_raw) > 0))
    conclusion = str(payload.get("conclusion") or "")

    factors: list[str] = []
    for item in factors_raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("point") or ""
            contrib = item.get("contribution")
            factors.append(f"{name}（贡献 {contrib}）" if contrib is not None else str(name))
        else:
            factors.append(str(item))

    citation = ""
    for m in metrics_used:
        if isinstance(m, dict) and m.get("口径"):
            citation = str(m.get("口径"))
            break
    if not citation and isinstance(metric, dict) and metric.get("citation"):
        citation = str(metric["citation"])

    charts = []
    for s in series:
        if isinstance(s, dict) and len(s.get("points") or []) >= 3:
            charts.append(
                {
                    "type": "line",
                    "title": s.get("label") or "趋势",
                    "x_field": "x",
                    "y_field": "y",
                    "data": s.get("points") or [],
                }
            )

    ctx.run_step("attribution-methodology", 3, f"LLM 归纳 {len(factors)} 条因子")
    analysis = {
        "sufficient": sufficient,
        "conclusion": conclusion,
        "factors": factors,
        "findings": findings,
        "metrics_used": metrics_used,
        "citation": citation,
        "reason": payload.get("need_more") or "",
    }
    if isinstance(metric, dict) and metric.get("name"):
        analysis["metric"] = metric
    trace = [ctx.trace_entry(subtask_id="analyst", summary=conclusion[:48] or f"LLM 分析 {len(factors)} 因子")]
    return {**ctx.to_state_patch(), "analysis": analysis, "charts": charts, "trace": trace}


def _evidence_preview(state: AgentState) -> str:
    parts: list[str] = []
    for block in state.get("evidence") or []:
        l3 = block.get("l3_id") or block.get("kind")
        if block.get("kind") == "documents":
            parts.append(f"doc:{len(block.get('hits') or [])} hits")
        else:
            parts.append(f"{l3}:{len(block.get('rows') or [])} rows")
    return "; ".join(parts[:8])
