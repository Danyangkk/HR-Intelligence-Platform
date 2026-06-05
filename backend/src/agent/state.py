from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict


Intent = Literal["chitchat", "policy", "lookup", "list", "aggregate", "compare", "trend", "attribution", "forecast"]


def _merge_dict(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(left or {})
    out.update(right or {})
    return out


def _merge_list(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    if not right:
        return list(left or [])
    if isinstance(right, list) and right and isinstance(right[0], dict) and right[0].get("__reset__"):
        return []
    return list(left or []) + list(right)


class AgentState(TypedDict, total=False):
    question: str
    role: str
    # 薪资权限相关：必须在 TypedDict 中声明，否则 langgraph 用 schema 过滤 initial
    # 时会丢弃这两个键，导致 planner 永远读不到 confirmed=True，陷入无限确认循环
    payroll_access: bool
    payroll_confirmed: bool
    intent: Intent | str
    entities: Annotated[dict[str, Any], _merge_dict]
    plan: list[dict[str, Any]]
    plan_index: int
    current_subtask: dict[str, Any] | None
    fetch_l3_id: str
    evidence: Annotated[list[dict[str, Any]], _merge_list]
    analysis: dict[str, Any]
    charts: list[dict[str, Any]]
    citations: Annotated[list[dict[str, Any]], _merge_list]
    trace: Annotated[list[dict[str, Any]], _merge_list]
    active_skills: list[dict[str, Any]]
    sop_executed: Annotated[list[dict[str, Any]], _merge_list]
    final: str
    rejected: bool
    reject_reason: str
    short_circuit: bool
    unmatched: bool
    clarify: dict[str, Any] | None
    history: list[dict[str, Any]]
    replan_count: int
    replan_gaps: list[str]
    broaden_search: bool
    critic_sufficient: bool
    critic_note: str
    limitation: str
    flow_timeout: bool
    harness_error: str
