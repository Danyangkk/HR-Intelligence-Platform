from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.state import AgentState

if TYPE_CHECKING:
    from src.agent.harness.context import HarnessContext
from src.models import AgentNodeTrace, AgentRun


def resolve_auto_badcase(
    *,
    outcome: str,
    signals: list[str],
) -> tuple[bool, str | None]:
    reasons = list(dict.fromkeys(signals))
    if outcome == "timeout":
        reasons.append("timeout")
    if outcome == "clarify":
        reasons.append("clarify")
    if not reasons:
        return False, None
    return True, "|".join(reasons)


async def create_agent_run_row(harness: HarnessContext) -> None:
    harness.db.add(
        AgentRun(
            id=harness.run_id,
            session_id=harness.session_id,
            role=harness.role,
            question_hash=harness.question_hash,
            intent="",
            outcome="running",
            replan_count=0,
            node_count=0,
            total_ms=0,
        )
    )
    await harness.db.flush()


async def persist_node_trace_row(db: AsyncSession, row: AgentNodeTrace) -> None:
    db.add(row)
    await db.flush()


async def finalize_agent_run_row(
    db: AsyncSession,
    harness: HarnessContext,
    *,
    state: AgentState,
    outcome: str,
    reject_reason: str | None,
    duration_ms: int,
) -> None:
    run = await db.get(AgentRun, harness.run_id)
    if not run:
        return
    run.intent = str(state.get("intent") or "")
    run.outcome = outcome
    run.reject_reason = reject_reason
    run.replan_count = int(state.get("replan_count") or 0)
    run.node_count = harness.node_count
    run.total_ms = duration_ms
    auto_badcase, badcase_reason = resolve_auto_badcase(
        outcome=outcome,
        signals=list(harness.badcase_signals),
    )
    run.auto_badcase = auto_badcase
    if badcase_reason and not run.badcase_reason:
        run.badcase_reason = badcase_reason
    if auto_badcase and run.review_status == "pending":
        run.review_status = "pending"
    await db.commit()
