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


# 薪资明细各类对应的 L3 主表（个人记录维度，不含汇总/审批表）
# 详见 backend/src/seed/generated/categories.json L2-4-x 节点。
_PAYROLL_L3_GROUPS: dict[str, list[str]] = {
    "wage": ["l3-4-1-4"],          # 工资发放明细表-网银报盘
    "bonus": ["l3-4-2-2"],         # 月度奖金发放明细表
    "social": ["l3-4-3-1"],        # 社保公积金账单
    "equity": ["l3-4-5-1", "l3-4-5-2"],  # 股权授予/归属记录
}
# 默认宽泛"薪资"问法的查询集（工资 + 奖金 + 社保三张明细主表）
_PAYROLL_L3_DEFAULT: list[str] = ["l3-4-1-4", "l3-4-2-2", "l3-4-3-1"]

_PAYROLL_FIELD_HINTS: dict[str, tuple[str, ...]] = {
    "wage":   ("工资", "薪水", "月薪", "工资条", "工资单", "底薪", "应发", "实发"),
    "bonus":  ("奖金", "年终奖", "绩效奖", "项目奖", "提成", "津贴", "补贴"),
    "social": ("社保", "公积金", "五险一金", "养老金", "医保", "失业金"),
    "equity": ("股权", "期权", "限制性股票"),
}


def pick_payroll_l3s(question: str) -> list[str]:
    """根据问题里提到的具体薪酬字段，选要查询的 L3 明细表集合。

    设计：
    - 命中具体字段（工资/奖金/社保/股权）→ 收窄到对应组（可叠加，如"工资和奖金"→两张表）。
    - 未命中具体字段或仅含宽泛词（薪资/薪酬/收入/到手）→ 默认查工资+奖金+社保三张明细主表。

    注意：这是"技术性选表"，不是"安全判定"。安全判定由 Planner 的 payroll_sensitive 决定。
    选错表无安全风险（最多多查/少查一张），Retriever 仍按工号/事业部筛后由 Composer 归纳。
    """
    q = question.strip()
    matched: list[str] = []
    seen: set[str] = set()
    for group, hints in _PAYROLL_FIELD_HINTS.items():
        if any(h in q for h in hints):
            for l3 in _PAYROLL_L3_GROUPS[group]:
                if l3 not in seen:
                    seen.add(l3)
                    matched.append(l3)
    return matched or list(_PAYROLL_L3_DEFAULT)


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
