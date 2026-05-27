from __future__ import annotations

import re
from typing import Any

from src.agent.state import AgentState

_SENSITIVE_KEYS = frozenset(
    {
        "question",
        "reply",
        "final",
        "answer",
        "text",
        "chunk",
        "payload",
        "rows",
        "hits",
        "evidence",
        "citations",
        "analysis",
        "entities",
        "employee",
        "姓名",
        "工号",
        "实发合计",
        "工资",
        "薪资",
        "身份证",
        "银行",
    }
)
_SALARY_FIELD_RE = re.compile(r"(工资|薪资|薪酬|实发|到手|奖金|个税|银行账号)", re.I)


def sanitize_decision(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in _SENSITIVE_KEYS:
                continue
            if isinstance(key, str) and _SALARY_FIELD_RE.search(key):
                continue
            out[key] = sanitize_decision(item)
        return out
    if isinstance(value, list):
        return [sanitize_decision(item) for item in value[:20]]
    if isinstance(value, str):
        if len(value) > 120 or _SALARY_FIELD_RE.search(value):
            return None
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(type(value).__name__)


def _count_structured_rows(evidence: list[dict[str, Any]] | None) -> tuple[int, list[str]]:
    total = 0
    masked: list[str] = []
    for block in evidence or []:
        if block.get("kind") == "documents":
            continue
        rows = block.get("rows") or []
        total += len(rows)
        l3_id = block.get("l3_id")
        if l3_id and isinstance(l3_id, str):
            masked.append(l3_id)
    return total, list(dict.fromkeys(masked))


def _count_doc_hits(evidence: list[dict[str, Any]] | None) -> int:
    total = 0
    for block in evidence or []:
        if block.get("kind") == "documents":
            total += len(block.get("hits") or [])
    return total


def _pii_masked_fields(state: AgentState, result: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    merged = list(state.get("evidence") or [])
    for block in result.get("evidence") or []:
        if isinstance(block, dict):
            merged.append(block)
    for block in merged:
        for row in block.get("rows") or []:
            if not isinstance(row, dict):
                continue
            for key in row.keys():
                if isinstance(key, str) and _SALARY_FIELD_RE.search(key):
                    fields.append(key)
    return list(dict.fromkeys(fields))


def extract_decision(
    node_name: str,
    result: dict[str, Any],
    state: AgentState,
) -> dict[str, Any]:
    decision: dict[str, Any] = {}
    trace_entry = (result.get("trace") or [None])[-1] or {}

    if node_name == "planner":
        if result.get("short_circuit"):
            decision["intent"] = result.get("intent") or "chitchat"
            decision["short_circuit"] = True
        elif result.get("rejected"):
            decision["rejected"] = True
            if result.get("unmatched"):
                decision["unmatched"] = True
        else:
            decision["intent"] = result.get("intent")
            if result.get("intent") == "aggregate":
                decision["forced_aggregate"] = True
    elif node_name == "resolver":
        if result.get("clarify"):
            decision["clarify"] = True
            decision["kind"] = (result.get("clarify") or {}).get("kind") or "unknown"
    elif node_name in {"retrieve", "retrieve_worker", "retrieve_collect"}:
        merged_evidence = list(state.get("evidence") or []) + list(result.get("evidence") or [])
        rows, l3_ids = _count_structured_rows(merged_evidence)
        decision["path"] = "structured"
        decision["rows_returned"] = rows
        if l3_ids:
            decision["l3_id"] = l3_ids[0]
            if len(l3_ids) > 1:
                decision["l3_ids"] = l3_ids
        masked = _pii_masked_fields(state, result)
        if masked:
            decision["pii_masked"] = masked
    elif node_name == "document":
        merged_evidence = list(state.get("evidence") or []) + list(result.get("evidence") or [])
        hits = _count_doc_hits(merged_evidence)
        if not hits:
            hits = len(result.get("citations") or [])
        decision["path"] = "rag"
        decision["chunks_hit"] = hits
        subtask = state.get("current_subtask") or {}
        targets = subtask.get("target_l3") or []
        if targets:
            decision["l3_id"] = targets[0]
    elif node_name == "analyst":
        decision["charts"] = len(result.get("charts") or state.get("charts") or [])
        analysis = result.get("analysis") or state.get("analysis") or {}
        if "sufficient" in analysis:
            decision["sufficient"] = bool(analysis.get("sufficient"))
    elif node_name == "critic":
        if result.get("needs_replan"):
            decision["decision"] = "replan"
            decision["gaps_count"] = 1
        elif result.get("limitation"):
            decision["decision"] = "pass_with_limit"
        else:
            decision["decision"] = "pass"
    elif node_name == "composer":
        citations = result.get("citations") or state.get("citations") or []
        decision["citations"] = len(citations)
        decision["charts"] = len(result.get("charts") or state.get("charts") or [])
        if result.get("final"):
            decision["composed"] = True
    elif node_name == "supervisor":
        sub = state.get("current_subtask") or {}
        decision["dispatch"] = sub.get("type") or "compose"
    elif node_name == "replan":
        decision["replan_count"] = int(result.get("replan_count") or 0)

    if trace_entry.get("subtask_id"):
        decision["subtask_id"] = trace_entry.get("subtask_id")

    return sanitize_decision(decision) or {}


def extract_skills(result: dict[str, Any], state: AgentState) -> list[dict[str, str]]:
    skills: list[dict[str, str]] = []
    for item in result.get("active_skills") or state.get("active_skills") or []:
        if isinstance(item, dict) and item.get("id"):
            skills.append({"id": str(item["id"]), "name": str(item.get("name") or item["id"])})
    trace_entry = (result.get("trace") or [None])[-1] or {}
    skill_label = trace_entry.get("skill")
    if skill_label and not skills:
        skills.append({"id": "unknown", "name": str(skill_label)})
    return skills[:8]


def extract_tools(result: dict[str, Any]) -> list[dict[str, Any]]:
    trace_entry = (result.get("trace") or [None])[-1] or {}
    tools = trace_entry.get("tools") or []
    return [{"name": str(name)} for name in tools if name]
