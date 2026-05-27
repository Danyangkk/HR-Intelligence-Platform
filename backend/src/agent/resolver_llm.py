"""Resolver LLM path — LLM draft + DB/dictionary validation + structured clarify."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.clarify_helpers import match_clarify_option
from src.agent.llm_runner import agent_llm_enabled, llm_json
from src.agent.prompts import RESOLVER_SYSTEM
from src.agent.resolver_finalize import finalize_resolver_entities
from src.agent.skills.runner import begin_agent_run
from src.agent.state import AgentState


async def resolve_entities_with_llm(db: AsyncSession, state: AgentState) -> dict[str, Any] | None:
    if not agent_llm_enabled():
        return None

    ctx = begin_agent_run("Resolver", state, subtask_type="resolve")
    ctx.run_step("entity-resolution", 1, "LLM 解析实体（校验层落地）")

    prefill = dict(state.get("entities") or {})
    if prefill.get("employee", {}).get("工号") and (
        prefill.get("lookup_scope") or match_clarify_option(state.get("question") or "", state.get("history"))
    ):
        ctx.run_step("entity-resolution", 2, "澄清后续 · DB 校验")
        return await finalize_resolver_entities(db, state, ctx, prefill, source="llm+prefill")

    user = _build_user_prompt(state)
    payload = llm_json(
        agent="Resolver",
        system=RESOLVER_SYSTEM,
        user=user,
        state=state,
        subtask_type="resolve",
    )
    if not payload:
        return None

    draft = payload.get("entities") if isinstance(payload.get("entities"), dict) else {}
    metric_query = str(payload.get("metric_query") or payload.get("metric") or "")
    if not draft and not metric_query and not payload.get("topic"):
        return None

    ctx.run_step("entity-resolution", 2, "LLM 草稿 → DB/字典校验")
    return await finalize_resolver_entities(
        db,
        state,
        ctx,
        draft,
        metric_query=metric_query,
        source="llm",
    )


def _build_user_prompt(state: AgentState) -> str:
    parts = [
        f"用户问题：{state.get('question', '')}",
        f"意图：{state.get('intent')}",
    ]
    if state.get("entities"):
        parts.append(f"已有 entities：{state.get('entities')}")
    parts.append(
        "只输出 JSON，不要 clarify 字段："
        '{"entities":{"employee":{},"org":{},"time_range":"","topic":"","lookup_scope":""},'
        '"metric_query":"模糊指标短语，如绩效很差/成本高"}'
    )
    return "\n\n".join(parts)
