"""复盘 finding 业务摘要校验：biz_problem 不得含技术术语。"""
from __future__ import annotations

import re
from typing import Any

# 复盘 Agent 规格 §5 禁用词（finding biz_problem + suggestion content_biz）
BIZ_TEXT_BANNED_RE = re.compile(
    r"(?i)"
    r"\b(?:rag|planner|router|retriever|guardrail|supervisor|clarifier|aggregate)\b"
    r"|over[_\s-]?reject|0\s*命中|run[_\s-]?id|chunks?_hit"
    r"|检索|意图识别|意图分布|badcase|few[\s-]?shot|embedding|token"
    r"|node[_\s-]?clue|sql|jsonb|llm|prompt|skill|trace|fan[\s-]?out"
    r"|§|\.yaml|\.md|tests/|ROUTER|PLANNER|PLANNER_FEW_SHOT",
)

# 向后兼容
BIZ_PROBLEM_BANNED_RE = BIZ_TEXT_BANNED_RE

PRIORITY_ZH = {"high": "高", "medium": "中", "low": "低"}


def validate_biz_problem(text: str | None) -> dict[str, Any]:
    """返回 {ok, issues}；issues 为命中禁用词列表。"""
    return _validate_biz_text(text, empty_msg="biz_problem 为空")


def validate_content_biz(text: str | None) -> dict[str, Any]:
    """建议 content_biz 人话校验。"""
    return _validate_biz_text(text, empty_msg="content_biz 为空")


def _validate_biz_text(text: str | None, *, empty_msg: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {"ok": False, "issues": [empty_msg]}
    issues: list[str] = []
    for m in BIZ_TEXT_BANNED_RE.finditer(raw):
        issues.append(m.group(0))
    seen: set[str] = set()
    uniq: list[str] = []
    for x in issues:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return {"ok": len(uniq) == 0, "issues": uniq}


def format_draft_changes(draft: dict[str, Any] | None) -> str:
    """技术超管展示用：draft_changes → 单行摘要。"""
    if not draft:
        return "—"
    parts: list[str] = []
    if draft.get("target"):
        parts.append(f"改动：{draft['target']}")
    if draft.get("action"):
        parts.append(f"方案：{draft['action']}")
    if draft.get("add_test_case"):
        parts.append(f"测试：{draft['add_test_case']}")
    return " · ".join(parts) if parts else "—"


def priority_label(priority: str | None) -> str:
    return PRIORITY_ZH.get((priority or "").strip().lower(), priority or "—")
