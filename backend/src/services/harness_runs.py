from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import AgentNodeTrace, AgentRun
from src.services.rbac import can_view_audit


def _serialize_run(row: AgentRun, *, include_traces: bool = False) -> dict[str, Any]:
    item: dict[str, Any] = {
        "run_id": str(row.id),
        "session_id": row.session_id,
        "role": row.role,
        "question_hash": row.question_hash,
        "intent": row.intent,
        "outcome": row.outcome,
        "reject_reason": row.reject_reason,
        "replan_count": row.replan_count,
        "node_count": row.node_count,
        "total_ms": row.total_ms,
        "user_feedback": row.user_feedback,
        "auto_badcase": row.auto_badcase,
        "badcase_reason": row.badcase_reason,
        "review_status": row.review_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_traces:
        item["nodes"] = [_serialize_node_trace(node) for node in sorted(row.node_traces or [], key=lambda n: n.seq)]
    return item


def _serialize_node_trace(row: AgentNodeTrace) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "node": row.node,
        "agent": row.agent,
        "skills_loaded": row.skills_loaded or [],
        "tools_called": row.tools_called or [],
        "status": row.status,
        "attempt": row.attempt,
        "duration_ms": row.duration_ms,
        "decision": row.decision or {},
        "error_type": row.error_type,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def list_harness_runs(
    db: AsyncSession,
    *,
    role: str,
    page: int = 1,
    page_size: int = 20,
    outcome: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    if not can_view_audit(role):
        return {"items": [], "total": 0, "pagination": {"page": page, "page_size": page_size, "total": 0}}

    query = select(AgentRun)
    if outcome:
        query = query.where(AgentRun.outcome == outcome.strip())
    if session_id:
        query = query.where(AgentRun.session_id == session_id.strip())

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = max(page - 1, 0) * page_size
    result = await db.execute(query.order_by(desc(AgentRun.created_at)).offset(offset).limit(page_size))
    items = [_serialize_run(row) for row in result.scalars().all()]
    return {
        "items": items,
        "total": total,
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


async def get_harness_run(
    db: AsyncSession,
    *,
    role: str,
    run_id: str,
) -> dict[str, Any] | None:
    if not can_view_audit(role):
        return None
    try:
        parsed = uuid.UUID(run_id)
    except ValueError:
        return None

    result = await db.execute(
        select(AgentRun)
        .options(selectinload(AgentRun.node_traces))
        .where(AgentRun.id == parsed)
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return _serialize_run(row, include_traces=True)
