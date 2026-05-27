"""Agent LLM execution framework — JSON output + skill context + rules fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from src.agent.prompts import with_global_preamble
from src.agent.skills.loader import skills_for_agent
from src.agent.skills.runner import SkillRunContext, begin_agent_run
from src.agent.state import AgentState
from src.core.config import get_settings
from src.services.llm.dashscope import chat_completion

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def agent_llm_enabled() -> bool:
    settings = get_settings()
    if settings.agent_llm_enabled is False:
        return False
    return bool((settings.dashscope_api_key or "").strip())


def build_skill_context(agent: str, state: AgentState, *, subtask_type: str | None = None) -> str:
    intent = state.get("intent")
    skills = skills_for_agent(agent, intent=str(intent) if intent else None, subtask_type=subtask_type)
    parts: list[str] = []
    for skill in skills[:4]:
        body = (skill.get("content") or "").strip()
        if body:
            parts.append(f"### Skill: {skill.get('name') or skill['id']}\n{body[:2000]}")
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
