"""Agent LLM execution framework — JSON output + skill context + rules fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from src.agent.prompts import with_global_preamble
from src.agent.skills.loader import load_skill, primary_skills_for, skill_meta, skills_for_agent
from src.agent.skills.runner import SkillRunContext, begin_agent_run
from src.agent.state import AgentState
from src.core.config import get_settings
from src.services.llm.dashscope import chat_completion

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_CHAPTER_HEADING = re.compile(r"^## ", re.MULTILINE)
_TIER2_TOTAL_BUDGET = 8000
_TIER2_PER_SKILL_BUDGET = 6000


def agent_llm_enabled() -> bool:
    settings = get_settings()
    if settings.agent_llm_enabled is False:
        return False
    return bool((settings.dashscope_api_key or "").strip())


def _retrieve_mode_from_state(state: AgentState) -> str | None:
    plan = state.get("plan") or []
    idx = state.get("plan_index") or 0
    if idx >= len(plan):
        return None
    mode = plan[idx].get("retrieve_mode")
    return str(mode) if mode else None


def _truncate_skill_body(body: str, max_chars: int) -> str:
    body = body.strip()
    if len(body) <= max_chars:
        return body
    chapter_starts = [match.start() for match in _CHAPTER_HEADING.finditer(body)]
    if len(chapter_starts) > 1:
        best = body[:max_chars]
        for start in chapter_starts[1:]:
            chunk = body[:start].rstrip()
            if len(chunk) <= max_chars:
                best = chunk
            else:
                break
        if len(best) < len(body):
            return f"{best}\n\n（后续章节略）"
    return f"{body[:max_chars]}\n\n（后续章节略）"


def build_skill_context(agent: str, state: AgentState, *, subtask_type: str | None = None) -> str:
    intent = state.get("intent")
    intent_str = str(intent) if intent else None
    bound = skills_for_agent(agent, intent=intent_str, subtask_type=subtask_type)
    if not bound:
        return ""

    summary_lines: list[str] = ["[可用方法论简表]"]
    for skill in bound:
        sid = str(skill.get("id") or "")
        meta = skill_meta(sid)
        description = meta.get("description") or meta.get("name") or sid
        summary_lines.append(f"- {sid}：{description}")

    retrieve_mode = _retrieve_mode_from_state(state)
    primary_ids = primary_skills_for(
        agent,
        subtask_type,
        intent_str,
        retrieve_mode,
    )

    parts: list[str] = ["\n".join(summary_lines)]
    if primary_ids:
        detail_lines: list[str] = ["[本步骤执行规范]"]
        remaining = _TIER2_TOTAL_BUDGET
        for sid in primary_ids:
            if remaining <= 0:
                break
            skill = load_skill(sid)
            body = (skill.get("content") or "").strip()
            if not body:
                continue
            per_skill_limit = min(_TIER2_PER_SKILL_BUDGET, remaining)
            if len(body) > per_skill_limit:
                body = _truncate_skill_body(body, per_skill_limit)
            remaining -= len(body)
            detail_lines.append(f"=== {sid}（全文）===\n{body}")
        parts.append("\n\n".join(detail_lines))

    return "\n\n".join(parts)


def parse_json_response(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    stripped = text.strip()
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(stripped)
    if match:
        try:
            payload = json.loads(match.group(1))
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            return None
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            payload = json.loads(stripped[start : end + 1])
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def llm_json(
    *,
    agent: str,
    system: str,
    user: str,
    state: AgentState,
    subtask_type: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 1200,
) -> dict[str, Any] | None:
    if not agent_llm_enabled():
        return None
    skill_ctx = build_skill_context(agent, state, subtask_type=subtask_type)
    full_system = with_global_preamble(system)
    if skill_ctx:
        full_system += f"\n\n## 已加载 Skills\n{skill_ctx}"
    raw = chat_completion(
        messages=[
            {"role": "system", "content": full_system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return parse_json_response(raw or "")


def merge_trace(ctx: SkillRunContext, subtask_id: str, summary: str, patch: dict[str, Any]) -> dict[str, Any]:
    patch = dict(patch)
    patch.setdefault("trace", [ctx.trace_entry(subtask_id=subtask_id, summary=summary)])
    if "sop_executed" not in patch:
        patch.update(ctx.to_state_patch())
    return patch
