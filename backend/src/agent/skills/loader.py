"""Load SKILL.md resources and map agents to skills."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_SKILLS_ROOT = Path(__file__).resolve().parent
_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# 通用型 G1–G11 + 流程型 P1–P8 + intent-planning（Planner trace 用）
SKILL_IDS = (
    "entity-resolution",  # G1
    "structured-retrieval",  # G2
    "document-rag",  # G3
    "attribution-methodology",  # G4
    "compare-benchmark",  # G5
    "trend-analysis",  # G6
    "metric-dictionary",  # G7
    "data-visualization",  # G8
    "pii-permission",  # G9
    "answer-composition",  # G10
    "evidence-validation",  # G11
    "process-resignation-attribution",  # P1
    "process-performance-diagnosis",  # P2
    "process-onboarding",  # P3
    "process-leave-policy",  # P4
    "process-compensation-review",  # P5
    "process-headcount-planning",  # P6
    "process-attendance-anomaly",  # P7
    "process-turnover-risk-alert",  # P8
    "intent-planning",  # Planner trace label
)

SKILL_DISPLAY: dict[str, str] = {
    "entity-resolution": "实体解析",
    "structured-retrieval": "结构化取数",
    "document-rag": "文档检索与解读",
    "attribution-methodology": "归因分析方法论",
    "compare-benchmark": "对比与基准",
    "trend-analysis": "趋势分析",
    "metric-dictionary": "指标口径字典",
    "data-visualization": "数据可视化",
    "pii-permission": "脱敏与权限",
    "answer-composition": "答案组织与引用",
    "evidence-validation": "证据校验",
    "process-resignation-attribution": "离职归因",
    "process-performance-diagnosis": "个人绩效诊断",
    "process-onboarding": "入职办理",
    "process-leave-policy": "请假制度解读",
    "process-compensation-review": "薪酬复盘",
    "process-headcount-planning": "编制规划",
    "process-attendance-anomaly": "考勤异常诊断",
    "process-turnover-risk-alert": "离职风险预警",
    "intent-planning": "意图识别与任务规划",
}

AGENT_SKILLS: dict[str, list[str]] = {
    "Planner": [],
    "Resolver": ["entity-resolution", "metric-dictionary"],
    "Retriever": ["structured-retrieval", "document-rag", "pii-permission", "metric-dictionary"],
    "Analyst": [
        "process-resignation-attribution",
        "process-performance-diagnosis",
        "process-turnover-risk-alert",
        "attribution-methodology",
        "compare-benchmark",
        "trend-analysis",
        "metric-dictionary",
    ],
    "Composer": ["data-visualization", "answer-composition"],
    "Critic": ["evidence-validation"],
}

SUBTASK_SKILLS: dict[str, list[str]] = {
    "resolve": ["entity-resolution"],
    "retrieve": ["structured-retrieval", "pii-permission"],
    "analyze": ["compare-benchmark", "attribution-methodology", "metric-dictionary"],
    "critique": ["evidence-validation"],
    "compose": ["answer-composition", "data-visualization"],
}

INTENT_PROCESS_SKILLS: dict[str, list[str]] = {
    "policy": ["process-leave-policy"],
    "lookup": [],
    "compare": ["process-headcount-planning"],
    "attribution": ["process-resignation-attribution", "process-performance-diagnosis"],
}


@lru_cache(maxsize=64)
def load_skill(skill_id: str) -> dict[str, Any]:
    path = _SKILLS_ROOT / skill_id / "SKILL.md"
    if not path.exists():
        return {"id": skill_id, "name": SKILL_DISPLAY.get(skill_id, skill_id), "content": ""}
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    title = meta.get("display_name") or SKILL_DISPLAY.get(skill_id, skill_id)
    if body:
        first = body.splitlines()[0].strip()
        if first.startswith("#"):
            title = first.lstrip("# ").strip() or title
    return {"id": skill_id, "name": title, "content": body, "meta": meta}


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, text[match.end() :]


def skills_for_agent(agent: str, *, intent: str | None = None, subtask_type: str | None = None) -> list[dict[str, Any]]:
    ids: list[str] = list(AGENT_SKILLS.get(agent, []))
    if intent:
        for sid in INTENT_PROCESS_SKILLS.get(intent, []):
            if sid not in ids:
                ids.append(sid)
    if subtask_type:
        for sid in SUBTASK_SKILLS.get(subtask_type, []):
            if sid not in ids:
                ids.insert(0, sid)
    return [load_skill(sid) for sid in ids if sid in SKILL_IDS or (_SKILLS_ROOT / sid / "SKILL.md").exists()]


def primary_skill_label(agent: str, *, subtask_type: str | None = None, intent: str | None = None) -> str:
    skills = skills_for_agent(agent, intent=intent, subtask_type=subtask_type)
    if not skills:
        return SKILL_DISPLAY.get(agent, agent)
    names = [s["name"] for s in skills[:2]]
    return " · ".join(names)


@lru_cache(maxsize=64)
def skill_meta(skill_id: str) -> dict[str, str]:
    loaded = load_skill(skill_id)
    meta = loaded.get("meta") or {}
    description = (meta.get("description") or "").strip()
    name = str(loaded.get("name") or SKILL_DISPLAY.get(skill_id, skill_id))
    return {"id": skill_id, "name": name, "description": description}


def primary_skills_for(
    agent: str,
    subtask_type: str | None,
    intent: str | None,
    retrieve_mode: str | None = None,
) -> list[str]:
    """Return ≤2 skill ids for tier-2 full-text injection (mapping table in PR8 doc)."""
    if not subtask_type:
        return []

    st = subtask_type.strip().lower()
    intent_key = (intent or "").strip().lower()

    if agent == "Resolver" and st == "resolve":
        return ["entity-resolution"]

    if agent == "Retriever" and st == "retrieve":
        mode = (retrieve_mode or "structured").strip().lower()
        if mode == "rag":
            return ["document-rag"]
        return ["structured-retrieval"]

    if agent == "Analyst" and st == "analyze":
        if intent_key == "compare":
            return ["compare-benchmark"]
        if intent_key == "attribution":
            primary = ["attribution-methodology"]
            for skill in skills_for_agent(agent, intent=intent, subtask_type=subtask_type):
                sid = str(skill.get("id") or "")
                if sid.startswith("process-") and sid not in primary:
                    primary.append(sid)
                    break
            return primary[:2]
        if intent_key in {"trend", "forecast"}:
            return ["trend-analysis"]
        return []

    if agent == "Critic" and st == "critique":
        return ["evidence-validation"]

    if agent == "Composer" and st == "compose":
        return ["answer-composition"]

    return []
