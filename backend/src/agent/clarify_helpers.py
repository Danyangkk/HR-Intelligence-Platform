"""Clarify payloads and multi-turn selection helpers (T-024)."""

from __future__ import annotations

import re
from typing import Any

_EMPLOYEE_ID_RE = re.compile(r"\b(A\d{4,})\b")

_LOOKUP_SCOPE_TARGETS: dict[str, list[str]] = {
    "overview": ["l3-5-1-1", "l3-2-2-1", "l3-2-2-4"],
    "performance": ["l3-5-1-1"],
    "leave": ["l3-2-2-1"],
    "attendance": ["l3-2-2-4"],
}

_VAGUE_LOOKUP_MARKERS = (
    "最近怎么样",
    "最近如何",
    "近况",
    "表现怎么样",
    "表现如何",
    "最近情况",
    "最近表现",
    "怎么样",
    "如何",
)


def employee_option_label(employee: dict[str, Any]) -> str:
    name = employee.get("姓名") or ""
    emp_no = employee.get("工号") or ""
    bu = employee.get("事业部") or ""
    dept = employee.get("部门") or ""
    return f"{name} {emp_no} · {bu} {dept}".strip()


def build_employee_clarify(name: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    options: list[dict[str, Any]] = []
    for candidate in candidates:
        employee = {
            "姓名": candidate.get("姓名"),
            "工号": candidate.get("工号"),
            "部门": candidate.get("部门"),
            "事业部": candidate.get("事业部") or candidate.get("公司"),
        }
        options.append(
            {
                "label": employee_option_label(employee),
                "value": str(employee.get("工号") or ""),
                "employee": employee,
            }
        )
    return {
        "kind": "employee",
        "question": f"有 {len(candidates)} 位「{name}」，您指哪位？",
        "options": options,
    }


def build_scope_clarify(name: str) -> dict[str, Any]:
    return {
        "kind": "scope",
        "question": f"您想了解 {name} 的哪方面？",
        "options": [
            {"label": "综合近况（绩效+请假+加班）", "value": "overview", "lookup_scope": "overview"},
            {"label": "绩效表现", "value": "performance", "lookup_scope": "performance"},
            {"label": "请假记录", "value": "leave", "lookup_scope": "leave"},
            {"label": "加班/考勤", "value": "attendance", "lookup_scope": "attendance"},
        ],
    }


def is_vague_lookup_question(question: str) -> bool:
    q = question.strip()
    if not q:
        return False
    if any(k in q for k in ("绩效", "请假", "假", "考勤", "加班", "排名", "等级", "几天", "多少")):
        return False
    return any(marker in q for marker in _VAGUE_LOOKUP_MARKERS)


def lookup_target_l3s(scope: str | None) -> list[str]:
    if scope and scope in _LOOKUP_SCOPE_TARGETS:
        return _LOOKUP_SCOPE_TARGETS[scope].copy()
    return ["l3-2-2-1"]


def clarify_options_for_history(clarify: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not clarify:
        return []
    options = clarify.get("options") or []
    return [opt for opt in options if isinstance(opt, dict)]


def match_clarify_option(question: str, history: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Match user follow-up to the last clarify options in history."""
    if not history:
        return None
    last = history[-1]
    options = clarify_options_for_history(last.get("clarify"))
    if not options:
        return None
    q = (question or "").strip()
    id_match = _EMPLOYEE_ID_RE.search(q)
    emp_id = id_match.group(1) if id_match else ""
    for opt in options:
        value = str(opt.get("value") or "")
        label = str(opt.get("label") or "")
        if emp_id and value == emp_id:
            return opt
        if label and (label in q or q in label):
            return opt
        if value and value in q:
            return opt
    return None


def apply_clarify_option(entities: dict[str, Any], option: dict[str, Any]) -> dict[str, Any]:
    out = dict(entities)
    if option.get("employee"):
        out["employee"] = dict(option["employee"])
    scope = str(option.get("lookup_scope") or option.get("value") or "")
    if scope in _LOOKUP_SCOPE_TARGETS:
        out["lookup_scope"] = scope
        out["target_l3"] = lookup_target_l3s(scope)
    return out


def effective_lookup_question(state: dict[str, Any]) -> str:
    """Use the original user question when the current turn is a clarify follow-up."""
    history = state.get("history") or []
    if history and history[-1].get("clarify"):
        return str(history[-1].get("question") or state.get("question") or "")
    return str(state.get("question") or "")
