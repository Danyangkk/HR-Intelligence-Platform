from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AgentRunLog
from src.services.rbac import can_view_audit, normalize_role


def infer_tools_used(intent: str | None, trace: list[dict[str, Any]] | None) -> list[str]:
    tools: list[str] = []
    for item in trace or []:
        for name in item.get("tools") or []:
            if name not in tools:
                tools.append(name)
    intent = intent or ""
    if intent == "policy" and "search_documents" not in tools:
        tools.append("search_documents")
    if intent in {"lookup", "compare", "attribution"} and "query_structured" not in tools:
        tools.append("query_structured")
    if intent in {"compare", "attribution"} and "calc" not in tools:
        tools.append("calc")
    if intent == "compare" and "chart_render" not in tools:
        tools.append("chart_render")
    return list(dict.fromkeys(tools))


async def persist_agent_run(
    db: AsyncSession,
    *,
    session_id: str,
    actor: str | None,
    role: str,
    question: str,
    result: dict[str, Any],
    duration_ms: int,
) -> None:
    trace = result.get("trace") or []
    tools_used = infer_tools_used(result.get("intent"), trace)
    db.add(
        AgentRunLog(
            session_id=session_id,
            actor=actor,
            role=normalize_role(role),
            question=question.strip(),
            intent=str(result.get("intent") or ""),
            rejected=bool(result.get("rejected")),
            replan_count=int(result.get("replan_count") or 0),
            duration_ms=duration_ms,
            plan=result.get("plan") or [],
            trace=trace,
            tools_used=tools_used,
            detail={
                "evidence_count": result.get("evidence_count", 0),
                "limitation": result.get("limitation") or "",
                "clarify": result.get("clarify"),
            },
        )
    )
    await db.commit()


async def list_agent_runs(
    db: AsyncSession,
    *,
    role: str,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    if not can_view_audit(role):
        return {"items": [], "total": 0, "pagination": {"page": page, "page_size": page_size, "total": 0}}

    query = select(AgentRunLog)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = max(page - 1, 0) * page_size
    result = await db.execute(query.order_by(desc(AgentRunLog.id)).offset(offset).limit(page_size))
    items = [
        {
            "id": row.id,
            "session_id": row.session_id,
            "actor": row.actor,
            "role": row.role,
            "question": row.question,
            "intent": row.intent,
            "rejected": row.rejected,
            "replan_count": row.replan_count,
            "duration_ms": row.duration_ms,
            "tools_used": row.tools_used or [],
            "plan": row.plan or [],
            "trace": row.trace or [],
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
