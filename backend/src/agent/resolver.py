from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.resolver_finalize import finalize_resolver_entities
from src.agent.resolver_lookup import EmployeeLookupResult
from src.agent.skills.runner import begin_agent_run
from src.agent.state import AgentState

__all__ = ["EmployeeLookupResult", "resolve_entities", "resolve_entities_rules"]


async def resolve_entities(db: AsyncSession, state: AgentState) -> dict[str, Any]:
    from src.agent.resolver_llm import resolve_entities_with_llm

    llm_result = await resolve_entities_with_llm(db, state)
    if llm_result is not None:
        return llm_result
    return await resolve_entities_rules(db, state)


async def resolve_entities_rules(db: AsyncSession, state: AgentState) -> dict[str, Any]:
    ctx = begin_agent_run("Resolver", state, subtask_type="resolve")
    ctx.run_step("entity-resolution", 1, "规则解析实体（DB/字典校验）")
    return await finalize_resolver_entities(
        db,
        state,
        ctx,
        dict(state.get("entities") or {}),
        source="rules",
    )
