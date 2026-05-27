from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.harness.constants import FLOW_TIMEOUT_S
from src.agent.harness.file_log import log_run_end, log_run_start
from src.agent.state import AgentState
from src.services.harness_trace import create_agent_run_row, finalize_agent_run_row


def question_hash(question: str) -> str:
    return hashlib.sha256(question.strip().encode("utf-8")).hexdigest()


@dataclass
class HarnessContext:
    run_id: uuid.UUID
    session_id: str
    role: str
    question_hash: str
    flow_started_at: float
    db: AsyncSession
    actor: str | None = None
    node_seq: int = 0
    node_count: int = 0
    traces: list[dict[str, Any]] = field(default_factory=list)
    badcase_signals: list[str] = field(default_factory=list)
    run_persisted: bool = False
    finalized: bool = False


def get_harness(config: dict[str, Any] | None) -> HarnessContext | None:
    if not config:
        return None
    configurable = config.get("configurable") or {}
    harness = configurable.get("harness")
    return harness if isinstance(harness, HarnessContext) else None


async def create_harness_context(
    db: AsyncSession,
    *,
    session_id: str,
    role: str,
    question: str,
    actor: str | None = None,
    flow_started_at: float,
) -> HarnessContext:
    run_id = uuid.uuid4()
    ctx = HarnessContext(
        run_id=run_id,
        session_id=session_id,
        role=role,
        question_hash=question_hash(question),
        actor=actor,
        flow_started_at=flow_started_at,
        db=db,
    )
    await create_agent_run_row(ctx)
    ctx.run_persisted = True
    log_run_start(
        run_id=str(run_id),
        session_id=session_id,
        role=role,
        question_hash=ctx.question_hash,
        actor=actor,
    )
    return ctx


def flow_elapsed_s(harness: HarnessContext) -> float:
    import time

    return time.perf_counter() - harness.flow_started_at


def flow_timed_out(harness: HarnessContext) -> bool:
    return flow_elapsed_s(harness) >= FLOW_TIMEOUT_S


def infer_outcome(state: AgentState, *, flow_timeout: bool = False) -> tuple[str, str | None]:
    if flow_timeout:
        return "timeout", None
    if state.get("clarify"):
        return "clarify", None
    if state.get("short_circuit") and state.get("intent") == "chitchat":
        return "success", None
    if state.get("rejected"):
        reason = str(state.get("reject_reason") or "")
        if state.get("unmatched"):
            return "error", reason or "unmatched"
        if "薪资" in reason or "明细" in reason:
            return "reject", reason
        return "reject", reason or None
    if state.get("harness_error"):
        return "error", str(state.get("harness_error"))
    return "success", None


async def finalize_harness_run(
    harness: HarnessContext | None,
    state: AgentState,
    *,
    duration_ms: int,
    flow_timeout: bool = False,
) -> None:
    if not harness or harness.finalized or not harness.run_persisted:
        return
    outcome, reject_reason = infer_outcome(state, flow_timeout=flow_timeout)
    await finalize_agent_run_row(
        harness.db,
        harness,
        state=state,
        outcome=outcome,
        reject_reason=reject_reason,
        duration_ms=duration_ms,
    )
    log_run_end(
        run_id=str(harness.run_id),
        outcome=outcome,
        intent=str(state.get("intent") or ""),
        total_ms=duration_ms,
        node_count=harness.node_count,
        replan_count=int(state.get("replan_count") or 0),
        reject_reason=reject_reason,
    )
    harness.finalized = True
