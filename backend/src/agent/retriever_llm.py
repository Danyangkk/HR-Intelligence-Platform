"""Retriever LLM assist — suggest filter relaxation when structured fetch returns 0 rows."""

from __future__ import annotations

from typing import Any

from src.agent.llm_runner import agent_llm_enabled, llm_json
from src.agent.prompts import RETRIEVER_SYSTEM
from src.agent.state import AgentState

# Fields often missing in legacy/demo rows — safe to relax after empty fetch
_LEGACY_OPTIONAL_FILTERS = frozenset({"事业部"})


def rules_relaxed_filters(
    state: AgentState,
    l3_id: str,
    filters: dict[str, str],
) -> dict[str, str] | None:
    """Rule-based filter relaxation before LLM (fast path)."""
    if not filters:
        return None
    intent = state.get("intent")
    if l3_id == "l3-2-5-1" and intent in {"aggregate", "trend", "attribution"}:
        if filters.get("事业部") and not state.get("broaden_search"):
            relaxed = {key: value for key, value in filters.items() if key != "事业部"}
            if relaxed != filters:
                return relaxed
    return None


async def suggest_relaxed_filters(
    state: AgentState,
    *,
    l3_id: str,
    filters: dict[str, str],
    template_columns: list[str] | None = None,
) -> dict[str, str] | None:
    """When fetch returned 0 rows, suggest dropping one filter (rules first, then LLM)."""
    rules = rules_relaxed_filters(state, l3_id, filters)
    if rules is not None:
        return rules

    if not agent_llm_enabled() or not filters:
        return None

    columns = template_columns or []
    user = (
        f"l3_id={l3_id}\n"
        f"intent={state.get('intent')}\n"
        f"filters={filters}\n"
        f"template_columns={columns}\n"
        f"entities={state.get('entities')}\n"
        "结构化查询返回 0 行。是否应放宽某一筛选字段？"
        '只输出 JSON：{"drop_filter":"字段名或none","reason":""}'
    )
    payload = llm_json(
        agent="Retriever",
        system=RETRIEVER_SYSTEM,
        user=user,
        state=state,
        subtask_type="retrieve",
        max_tokens=300,
    )
    if not payload:
        return None

    drop = str(payload.get("drop_filter") or "none").strip()
    if drop.lower() in {"none", "无", ""}:
        return None
    if drop not in filters:
        return None
    if drop not in _LEGACY_OPTIONAL_FILTERS and drop not in columns:
        return None
    relaxed = {key: value for key, value in filters.items() if key != drop}
    return relaxed if relaxed != filters else None
