from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AgentFeedback, AgentRun
from src.services.rbac import can_view_audit

FeedbackRating = Literal["up", "down"]
FeedbackReason = Literal["wrong", "irrelevant", "bad_data", "over_reject", "other"]
ReviewStatus = Literal["pending", "reviewed", "fixed", "ignored"]

DOWN_REASONS = frozenset({"wrong", "irrelevant", "bad_data", "over_reject", "other"})


async def submit_agent_feedback(
    db: AsyncSession,
    *,
    run_id: str,
    rating: str,
    reason: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if rating not in {"up", "down"}:
        raise ValueError("rating must be up or down")
    if rating == "down":
        if reason not in DOWN_REASONS:
            raise ValueError("down rating requires a valid reason")
        if reason == "other" and not (note or "").strip():
            raise ValueError("other reason requires note")
    else:
        reason = None
        note = None

    try:
        parsed = uuid.UUID(run_id)
    except ValueError as exc:
        raise ValueError("invalid run_id") from exc

    run = await db.get(AgentRun, parsed)
    if not run:
        raise LookupError("run not found")

    row = AgentFeedback(
        run_id=parsed,
        rating=rating,
        reason=reason,
        note=(note or "").strip() or None,
    )
    db.add(row)
    run.user_feedback = rating
    if rating == "down":
        run.auto_badcase = True
        run.badcase_reason = "user_down"
        if run.review_status not in {"reviewed", "fixed", "ignored"}:
            run.review_status = "pending"
    await db.commit()
    return {"run_id": str(parsed), "rating": rating, "reason": reason}


async def list_badcases(
    db: AsyncSession,
    *,
    role: str,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    reason: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> dict[str, Any]:
    if not can_view_audit(role):
        return {"items": [], "total": 0, "pagination": {"page": page, "page_size": page_size, "total": 0}}

    query = select(AgentRun).where(
        or_(AgentRun.auto_badcase.is_(True), AgentRun.user_feedback == "down")
    )
    if status:
        query = query.where(AgentRun.review_status == status.strip())
    if reason:
        query = query.where(AgentRun.badcase_reason.contains(reason.strip()))
    if from_ts:
        query = query.where(AgentRun.created_at >= from_ts)
    if to_ts:
        query = query.where(AgentRun.created_at <= to_ts)

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = max(page - 1, 0) * page_size
    result = await db.execute(query.order_by(desc(AgentRun.created_at)).offset(offset).limit(page_size))
    items = [_serialize_badcase(row) for row in result.scalars().all()]
    return {
        "items": items,
        "total": total,
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


async def update_badcase_review(
    db: AsyncSession,
    *,
    role: str,
    run_id: str,
    review_status: str,
) -> dict[str, Any] | None:
    if not can_view_audit(role):
        return None
    if review_status not in {"pending", "reviewed", "fixed", "ignored"}:
        raise ValueError("invalid review_status")

    try:
        parsed = uuid.UUID(run_id)
    except ValueError as exc:
        raise ValueError("invalid run_id") from exc

    run = await db.get(AgentRun, parsed)
    if not run:
        return None
    if not run.auto_badcase and run.user_feedback != "down":
        raise ValueError("run is not a badcase")

    run.review_status = review_status
    await db.commit()
    return _serialize_badcase(run)


def _serialize_badcase(row: AgentRun) -> dict[str, Any]:
    return {
        "run_id": str(row.id),
        "session_id": row.session_id,
        "question_hash": row.question_hash,
        "intent": row.intent,
        "outcome": row.outcome,
        "badcase_reason": row.badcase_reason,
        "user_feedback": row.user_feedback,
        "auto_badcase": row.auto_badcase,
        "review_status": row.review_status,
        "replan_count": row.replan_count,
        "node_count": row.node_count,
        "total_ms": row.total_ms,
        "reject_reason": row.reject_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
