from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.graph import run_agent
from src.agent.stream import run_agent_stream
from src.api.deps import CurrentUser, get_current_user, get_optional_user, require_audit_view, resolve_role
from src.core.response import fail, ok
from src.db.session import get_db
from src.schemas.agent import AgentAskRequest, StructuredQueryRequest
from src.schemas.metrics import CalcRequest
from src.schemas.rag import DocumentSearchRequest
from src.services.agent.structured_query import query_structured
from src.services.agent_feedback import list_badcases, submit_agent_feedback, update_badcase_review
from src.services.agent_runs import infer_tools_used, list_agent_runs, persist_agent_run
from src.services.harness_runs import get_harness_run, list_harness_runs
from src.services.audit import list_audit_logs, write_audit
from src.services.metrics.calc import CalcError, calculate_metric, calculate_operation
from src.services.metrics.dictionary import get_metric, list_categories, list_metrics, search_metrics
from src.services.rbac import can_read_l3
from src.services.rag_search import search_documents
from src.schemas.feedback import AgentFeedbackRequest, BadcaseReviewUpdate

router = APIRouter(prefix="/agent", tags=["agent"])


async def _record_agent_session(
    db: AsyncSession,
    *,
    actor: str | None,
    role: str,
    question: str,
    result: dict[str, Any],
) -> None:
    session_id = result.get("session_id") or str(uuid.uuid4())
    duration_ms = int(result.get("duration_ms") or 0)
    await persist_agent_run(
        db,
        session_id=session_id,
        actor=actor,
        role=role,
        question=question,
        result=result,
        duration_ms=duration_ms,
    )
    await write_audit(
        db,
        actor=actor,
        action="agent.ask",
        target_id=session_id,
        detail={
            "question": question,
            "intent": result.get("intent"),
            "role": role,
            "rejected": result.get("rejected"),
            "replan_count": result.get("replan_count"),
            "duration_ms": duration_ms,
            "tools_used": infer_tools_used(result.get("intent"), result.get("trace")),
        },
    )


@router.get("/metrics")
async def metrics_dictionary(
    q: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    if q:
        items = search_metrics(q)
    else:
        items = list_metrics(category=category)
    return ok(
        {
            "total": len(items),
            "categories": list_categories(),
            "items": items,
        }
    )


@router.get("/metrics/{name}")
async def metric_detail(name: str) -> dict[str, Any]:
    item = get_metric(name)
    if not item:
        return fail(404, f"未知指标：{name}")
    return ok(item.to_dict())


@router.post("/calc")
async def calc(body: CalcRequest) -> dict[str, Any]:
    try:
        if body.metric and not body.operation:
            result = calculate_metric(body.metric, body.inputs)
        elif body.operation:
            result = calculate_operation(
                body.operation,
                numerator=body.numerator,
                denominator=body.denominator,
                current=body.current,
                previous=body.previous,
                metric=body.metric,
            )
        else:
            return fail(400, "请提供 metric 或 operation")
    except CalcError as exc:
        return fail(400, str(exc))
    return ok(result.to_dict())


@router.post("/query/structured")
async def agent_query_structured(
    body: StructuredQueryRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    role = resolve_role(user)
    if not can_read_l3(role, body.l3_id):
        return fail(403, "无权访问该数据表")
    try:
        data = await query_structured(
            db,
            l3_id=body.l3_id,
            filters=body.filters,
            search=body.search,
            page=body.page,
            page_size=body.page_size,
            role=role,
            group_by=body.group_by or None,
            aggregations=[a.model_dump() for a in body.aggregations] or None,
            limit=body.limit,
        )
    except ValueError as exc:
        return fail(400, str(exc))
    return ok(data)


@router.post("/query/documents")
async def query_documents(
    body: DocumentSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await search_documents(
        db,
        l3_id=body.l3_id,
        query=body.query,
        top_k=body.top_k,
        meta_filters=body.meta_filters,
        only_current=body.only_current,
    )
    return ok(
        {
            "l3_id": body.l3_id,
            "query": body.query,
            "hits": result["hits"],
            "found": result["found"],
            "mode": result["mode"],
        }
    )


@router.get("/runs")
async def agent_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    require_audit_view(user)
    data = await list_agent_runs(db, role=user.role, page=page, page_size=page_size)
    return ok(data)


@router.get("/harness/runs")
async def harness_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    outcome: str | None = Query(None, description="success|reject|clarify|timeout|error|running"),
    session_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    require_audit_view(user)
    data = await list_harness_runs(
        db,
        role=user.role,
        page=page,
        page_size=page_size,
        outcome=outcome,
        session_id=session_id,
    )
    return ok(data)


@router.get("/harness/runs/{run_id}")
async def harness_run_detail(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    require_audit_view(user)
    data = await get_harness_run(db, role=user.role, run_id=run_id)
    if not data:
        return fail(404, "run not found")
    return ok(data)


@router.get("/harness/badcases")
async def harness_badcases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="pending|reviewed|fixed|ignored"),
    reason: str | None = Query(None),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    require_audit_view(user)
    from datetime import datetime

    def _parse_ts(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    data = await list_badcases(
        db,
        role=user.role,
        page=page,
        page_size=page_size,
        status=status,
        reason=reason,
        from_ts=_parse_ts(from_ts),
        to_ts=_parse_ts(to_ts),
    )
    return ok(data)


@router.patch("/harness/badcases/{run_id}")
async def harness_badcase_review(
    run_id: str,
    body: BadcaseReviewUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    require_audit_view(user)
    try:
        data = await update_badcase_review(
            db,
            role=user.role,
            run_id=run_id,
            review_status=body.review_status,
        )
    except ValueError as exc:
        return fail(400, str(exc))
    if not data:
        return fail(404, "badcase not found")
    return ok(data)


@router.post("/feedback")
async def agent_feedback(
    body: AgentFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    try:
        data = await submit_agent_feedback(
            db,
            run_id=body.run_id,
            rating=body.rating,
            reason=body.reason,
            note=body.note,
        )
    except LookupError:
        return fail(404, "run not found")
    except ValueError as exc:
        return fail(400, str(exc))
    return ok(data)


@router.get("/audit/logs")
async def audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict[str, Any]:
    require_audit_view(user)
    data = await list_audit_logs(db, role=user.role, page=page, page_size=page_size, action=action)
    return ok(data)


@router.post("/ask")
async def agent_ask(
    body: AgentAskRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
):
    if not body.question.strip():
        return fail(400, "question 不能为空")

    role = resolve_role(user, body.role)
    session_id = str(uuid.uuid4())
    actor = None if user.username == "anonymous" else user.username

    if body.stream:
        return StreamingResponse(
            run_agent_stream(
                db,
                question=body.question,
                role=role,
                history=body.history,
                entities=body.entities,
                session_id=session_id,
                actor=actor,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Session-Id": session_id,
            },
        )

    result = await run_agent(
        db,
        question=body.question,
        role=role,
        history=body.history,
        entities=body.entities,
        session_id=session_id,
    )
    await _record_agent_session(db, actor=actor, role=role, question=body.question, result=result)
    return ok(result)
