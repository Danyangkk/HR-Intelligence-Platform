from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AuditLog
from src.services.rbac import can_view_audit, normalize_role


async def write_audit(
    db: AsyncSession,
    *,
    actor: str | None,
    action: str,
    l3_id: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor=actor,
            action=action,
            l3_id=l3_id,
            target_id=target_id,
            detail=detail or {},
        )
    )
    await db.commit()


async def list_audit_logs(
    db: AsyncSession,
    *,
    role: str,
    page: int = 1,
    page_size: int = 50,
    action: str | None = None,
) -> dict[str, Any]:
    if not can_view_audit(role):
        return {"items": [], "total": 0, "pagination": {"page": page, "page_size": page_size, "total": 0}}

    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = max(page - 1, 0) * page_size
    result = await db.execute(query.order_by(desc(AuditLog.id)).offset(offset).limit(page_size))
    items = [
        {
            "id": row.id,
            "actor": row.actor,
            "action": row.action,
            "l3_id": row.l3_id,
            "target_id": row.target_id,
            "detail": row.detail or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in result.scalars().all()
    ]
    return {
        "items": items,
        "total": total,
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }
