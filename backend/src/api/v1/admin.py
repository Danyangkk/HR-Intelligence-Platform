from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_user
from src.core.response import fail, ok
from src.db.session import get_db
from src.schemas.admin import (
    AdoptSuggestionRequest,
    CreateUserRequest,
    PayrollConfirmRequest,
    PayrollGrantRequest,
    PayrollRevokeRequest,
    RejectSuggestionRequest,
    TicketNoteRequest,
    UpdateUserRequest,
)
from src.services.audit import write_audit
from src.services.improvement_tickets import (
    MOCK_REVIEW_REPORT,
    MOCK_REVIEW_REPORTS,
    TicketTransitionError,
    accept_ticket,
    add_ticket_note,
    confirm_ticket_release,
    create_ticket_from_suggestion,
    defer_suggestion,
    get_ticket,
    list_mock_review_periods,
    list_mock_review_reports,
    list_tickets,
    mark_ticket_done,
    retest_ticket_gate,
    reject_suggestion,
    seed_demo_tickets,
    update_ticket_new_case_ids,
    withdraw_ticket,
)
from src.services.review_suggestions import (
    format_review_source,
    hold_review_suggestion,
    list_hold_pending_suggestions,
    normalize_suggestion_modules,
    reject_review_suggestion,
)
from src.services.eval_service import (
    attach_run_metrics_from_cases,
    count_eval_runs,
    delete_garbage_eval_runs,
    get_eval_coverage,
    get_eval_run_detail,
    get_run_diff,
    list_eval_runs,
    resolve_gate_l1_threshold,
    resolve_gate_assert_threshold,
    set_eval_baseline,
    list_run_cases,
    submit_judge_feedback,
)
from src.eval.case_draft import list_eval_case_ids
from src.eval.demo_seed import seed_eval_demo
from src.services.payroll_access import (
    create_confirm_token,
    grant_payroll_access,
    list_payroll_access_logs,
    list_payroll_holders,
    revoke_payroll_access,
    validate_confirm_token,
)
from src.services.rbac import (
    TECH_SUPER_ADMIN,
    can_decide_review_suggestions,
    can_grant_payroll_access,
    can_manage_users,
    can_operate_tickets,
    can_track_tickets,
    can_view_payroll_audit,
    can_view_eval_center,
    can_view_review_reports,
    normalize_role,
)
from src.models import ImprovementTicket, User

router = APIRouter(prefix="/admin", tags=["admin"])


def _ticket_value_error_response(exc: ValueError) -> dict[str, Any]:
    msg = str(exc)
    if isinstance(exc, TicketTransitionError):
        return fail(422, msg)
    if "非法状态转移" in msg or "仅待处理工单" in msg:
        return fail(422, msg)
    if "工单未声明评测用例" in msg or "不在评测集中" in msg:
        return fail(422, msg)
    if "未经过评测门禁" in msg or "重新提测" in msg or "环境已变更" in msg:
        return fail(422, msg)
    return fail(400, msg)


def _require(user: CurrentUser, check) -> None:
    if not check(normalize_role(user.role)):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="forbidden")


async def _load_user(db: AsyncSession, user: CurrentUser) -> User:
    from sqlalchemy import select

    row = await db.scalar(select(User).where(User.username == user.username, User.is_active.is_(True)))
    if not row:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="user not found")
    return row


@router.get("/users")
async def admin_users(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    _require(user, can_manage_users)
    return ok({"items": await list_users(db)})


@router.post("/users")
async def admin_create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    actor = await _load_user(db, user)
    try:
        data = await create_user(
            db,
            actor=actor,
            username=body.username,
            password=body.password,
            role=body.role,
            display_name=body.display_name,
            employee_id=body.employee_id,
        )
    except PermissionError as exc:
        return fail(403, str(exc))
    except ValueError as exc:
        return fail(400, str(exc))
    return ok(data)


@router.patch("/users/{username}")
async def admin_update_user(
    username: str,
    body: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    actor = await _load_user(db, user)
    try:
        data = await update_user(
            db,
            actor=actor,
            username=username,
            role=body.role,
            display_name=body.display_name,
            is_active=body.is_active,
        )
    except PermissionError as exc:
        return fail(403, str(exc))
    except LookupError:
        return fail(404, "user not found")
    return ok(data)


@router.get("/payroll/holders")
async def payroll_holders(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    _require(user, can_grant_payroll_access)
    items = await list_payroll_holders(db)
    return ok({"items": items, "total": len(items)})


@router.post("/payroll/grant")
async def payroll_grant(
    body: PayrollGrantRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    actor = await _load_user(db, user)
    try:
        data = await grant_payroll_access(db, actor=actor, target_username=body.target_username, reason=body.reason)
    except PermissionError as exc:
        return fail(403, str(exc))
    except LookupError:
        return fail(404, "user not found")
    except ValueError as exc:
        return fail(400, str(exc))
    return ok(data)


@router.post("/payroll/revoke")
async def payroll_revoke(
    body: PayrollRevokeRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    actor = await _load_user(db, user)
    try:
        data = await revoke_payroll_access(
            db, actor=actor, target_username=body.target_username, reason=body.reason
        )
    except PermissionError as exc:
        return fail(403, str(exc))
    except LookupError:
        return fail(404, "user not found")
    return ok(data)


@router.post("/payroll/confirm-access")
async def payroll_confirm_access(
    body: PayrollConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    actor = await _load_user(db, user)
    try:
        data = await create_confirm_token(
            db,
            actor=actor,
            target_ref=body.target_ref,
            entry=body.entry,
            fields=body.fields,
            reason=body.reason,
        )
    except PermissionError as exc:
        return fail(403, str(exc))
    return ok(data)


@router.get("/payroll/access-logs")
async def payroll_access_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    _require(user, can_view_payroll_audit)
    return ok(await list_payroll_access_logs(db, page=page, page_size=page_size))


@router.get("/review/available-periods")
async def review_available_periods(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    """供前端筛选下拉列表用。"""
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_review_reports(normalize_role(user.role)):
        return fail(403, "forbidden")
    return ok({"periods": list_mock_review_periods()})


@router.get("/review/report")
async def review_report(
    week: str | None = Query(None, description="all|latest|<2026-Wxx>，默认 all 返回所有报告"),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """返回复盘报告列表（按时间倒序）。

    week 参数：
      - 不传 / 'all'：全部报告（默认）
      - 'latest'：最新一份
      - 具体周值如 '2026-W22'：仅返回该周
    """
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_review_reports(normalize_role(user.role)):
        return fail(403, "forbidden")
    role = normalize_role(user.role)
    items = list_mock_review_reports(week, role=role)
    view_mode = "tech_readonly" if role == TECH_SUPER_ADMIN else "biz_decision"
    return ok({"items": items, "total": len(items), "view_mode": view_mode})


@router.post("/review/suggestions/{suggestion_id}/adopt")
async def adopt_suggestion(
    suggestion_id: str,
    body: AdoptSuggestionRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_decide_review_suggestions(normalize_role(user.role)):
        return fail(403, "仅业务超管可采纳复盘建议")
    # 在所有 mock 报告里反查 suggestion_id，定位对应 report/finding（finding 通过 evidence_run_ids 桥接）
    matched_report, matched_suggestion, matched_finding_id = _locate_suggestion(suggestion_id, body)
    title, content_biz, draft, change_target, test_requirement = _resolve_adopt_payload(
        body, matched_suggestion
    )
    role = normalize_role(user.role)
    ticket = await create_ticket_from_suggestion(
        db,
        title=title,
        content_biz=content_biz,
        draft_changes=draft,
        source=format_review_source(
            period=(matched_report or {}).get("period"),
            week=(matched_report or {}).get("week"),
            label=(matched_report or {}).get("label"),
        )
        if matched_report
        else "复盘报告",
        change_target=change_target,
        test_requirement=test_requirement,
        evidence_run_ids=body.evidence_run_ids,
        source_type="review_report" if matched_report else "manual",
        source_report_id=(matched_report or {}).get("id"),
        source_finding_id=matched_finding_id or body.finding_id,
        source_suggestion_id=suggestion_id if matched_report else None,
        role=role,
    )
    return ok({"suggestion_id": suggestion_id, "ticket": ticket})


def _locate_suggestion(
    suggestion_id: str, body: AdoptSuggestionRequest
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    """在 MOCK_REVIEW_REPORTS 里反查 suggestion_id；同时按 evidence_run_ids 推断关联 finding。

    返回 (report, suggestion, finding_id)，全部允许为 None（兼容手动工单场景）。
    """
    target_report = None
    target_suggestion = None
    candidates = MOCK_REVIEW_REPORTS
    if body.report_id:
        candidates = [r for r in MOCK_REVIEW_REPORTS if r.get("id") == body.report_id] or candidates
    for report in candidates:
        for sug in report.get("suggestions") or []:
            if sug.get("id") == suggestion_id:
                target_report, target_suggestion = report, sug
                break
        if target_suggestion:
            break
    if not target_report:
        return None, None, None
    # 反查 finding：若客户端传了 finding_id 优先；否则按 evidence_run_ids 交集匹配
    finding_id = body.finding_id
    if not finding_id and target_suggestion:
        run_ids = set(target_suggestion.get("evidence_run_ids") or body.evidence_run_ids or [])
        for f in target_report.get("findings") or []:
            if run_ids & set(f.get("run_ids") or []):
                finding_id = f.get("id")
                break
    return target_report, target_suggestion, finding_id


def _resolve_adopt_payload(
    body: AdoptSuggestionRequest,
    matched_suggestion: dict[str, Any] | None,
) -> tuple[str, str, dict[str, Any], str | None, str | None]:
    """从请求 + mock suggestion 解析 content_biz / draft_changes。"""
    norm = normalize_suggestion_modules(matched_suggestion or {})
    draft = dict(norm.get("draft_changes") or {})
    content_biz = (
        (body.content_biz or body.content or norm.get("content_biz") or body.title or "")
        .strip()
    )
    if not content_biz:
        content_biz = "来自复盘报告的改进建议"
    title = (body.title or content_biz)[:256]
    change_target = body.change_target or draft.get("target")
    test_requirement = body.test_requirement or draft.get("add_test_case")
    if body.change_target and not draft.get("target"):
        draft["target"] = body.change_target
    if body.test_requirement and not draft.get("add_test_case"):
        draft["add_test_case"] = body.test_requirement
    if norm.get("draft_changes", {}).get("action") and not draft.get("action"):
        draft["action"] = norm["draft_changes"]["action"]
    return title, content_biz, draft, change_target, test_requirement


@router.get("/review/hold-pending")
async def review_hold_pending(
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """存疑待办（仅业务超管）。"""
    if not user.authenticated:
        return fail(401, "请先登录")
    if normalize_role(user.role) != "biz_super_admin":
        return fail(403, "forbidden")
    items = list_hold_pending_suggestions()
    return ok({"items": items, "total": len(items)})


@router.post("/review/suggestions/{suggestion_id}/reject")
async def review_suggestion_reject(
    suggestion_id: str,
    body: RejectSuggestionRequest,
    report_id: str | None = Query(None),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_decide_review_suggestions(normalize_role(user.role)):
        return fail(403, "仅业务超管可驳回复盘建议")
    try:
        return ok(
            reject_review_suggestion(
                suggestion_id, reason=body.reason, report_id=report_id
            )
        )
    except LookupError:
        return fail(404, "suggestion not found")
    except ValueError as exc:
        return fail(400, str(exc))


@router.post("/review/suggestions/{suggestion_id}/hold")
async def review_suggestion_hold(
    suggestion_id: str,
    report_id: str | None = Query(None),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_decide_review_suggestions(normalize_role(user.role)):
        return fail(403, "仅业务超管可标记存疑")
    try:
        return ok(hold_review_suggestion(suggestion_id, report_id=report_id))
    except LookupError:
        return fail(404, "suggestion not found")
    except ValueError as exc:
        return fail(400, str(exc))


@router.post("/review/suggestions/{suggestion_id}/readopt")
async def review_suggestion_readopt(
    suggestion_id: str,
    body: AdoptSuggestionRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """存疑待办 → 重新采纳生成工单（仅业务超管）。"""
    if not user.authenticated:
        return fail(401, "请先登录")
    if normalize_role(user.role) != "biz_super_admin":
        return fail(403, "forbidden")
    matched_report, matched_suggestion, matched_finding_id = _locate_suggestion(suggestion_id, body)
    if not matched_report:
        return fail(404, "suggestion not found")
    title, content_biz, draft, change_target, test_requirement = _resolve_adopt_payload(
        body, matched_suggestion
    )
    ticket = await create_ticket_from_suggestion(
        db,
        title=title,
        content_biz=content_biz,
        draft_changes=draft,
        source=format_review_source(
            period=matched_report.get("period"),
            week=matched_report.get("week"),
            label=matched_report.get("label"),
        ),
        change_target=change_target,
        test_requirement=test_requirement,
        evidence_run_ids=body.evidence_run_ids,
        source_type="review_report",
        source_report_id=matched_report.get("id"),
        source_finding_id=matched_finding_id or body.finding_id,
        source_suggestion_id=suggestion_id,
        role=normalize_role(user.role),
    )
    return ok({"suggestion_id": suggestion_id, "ticket": ticket})


@router.get("/tickets")
async def tickets_list(
    status: str | None = Query(None),
    mine: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    role = normalize_role(user.role)
    if mine and not can_operate_tickets(role):
        return fail(403, "forbidden")
    if not mine and not can_track_tickets(role):
        return fail(403, "forbidden")
    await seed_demo_tickets(db)
    return ok(await list_tickets(db, role=role, status=status, mine_only=mine, page=page, page_size=page_size))


@router.get("/tickets/{ticket_id}")
async def ticket_detail(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    role = normalize_role(user.role)
    if not can_track_tickets(role) and not can_operate_tickets(role):
        return fail(403, "forbidden")
    data = await get_ticket(db, ticket_id, role=role)
    if not data:
        return fail(404, "ticket not found")
    return ok(data)


@router.post("/tickets/{ticket_id}/accept")
async def ticket_accept(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_operate_tickets(normalize_role(user.role)):
        return fail(403, "forbidden")
    try:
        return ok(await accept_ticket(db, ticket_id))
    except LookupError:
        return fail(404, "ticket not found")
    except ValueError as exc:
        return _ticket_value_error_response(exc)


@router.patch("/tickets/{ticket_id}/new-cases")
async def ticket_update_new_cases(
    ticket_id: int,
    body: dict[str, Any] | None = None,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_operate_tickets(normalize_role(user.role)):
        return fail(403, "forbidden")
    raw = (body or {}).get("new_case_ids")
    if raw is None or not isinstance(raw, list):
        return fail(400, "new_case_ids must be a list")
    try:
        return ok(
            await update_ticket_new_case_ids(
                db,
                ticket_id,
                [str(x) for x in raw],
            )
        )
    except LookupError:
        return fail(404, "ticket not found")
    except ValueError as exc:
        return _ticket_value_error_response(exc)


@router.post("/tickets/{ticket_id}/complete")
async def ticket_complete(
    ticket_id: int,
    background_tasks: BackgroundTasks,
    body: dict[str, Any] | None = None,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_operate_tickets(normalize_role(user.role)):
        return fail(403, "forbidden")
    new_case_ids = (body or {}).get("new_case_ids")
    if new_case_ids is not None and not isinstance(new_case_ids, list):
        return fail(400, "new_case_ids must be a list")
    try:
        payload = await mark_ticket_done(
            db,
            ticket_id,
            new_case_ids=new_case_ids,
            triggered_by=user.username or TECH_SUPER_ADMIN,
        )
        gate_run = payload.get("gate_run") or {}
        run_id = gate_run.get("run_id")
        new_ids = gate_run.get("new_case_ids") or []

        from src.db.session import AsyncSessionLocal
        from src.eval.runner import finalize_gate_run_for_ticket, run_eval_batch
        from src.models import EvalRun

        async def _gate_bg(rid: int, tid: int, case_ids: list[str]) -> None:
            async with AsyncSessionLocal() as bg_db:
                try:
                    await run_eval_batch(
                        bg_db,
                        run_id=rid,
                        run_type="gate",
                        trigger="ticket_gate",
                        triggered_by=user.username,
                        new_case_ids=case_ids,
                    )
                    await finalize_gate_run_for_ticket(
                        bg_db, run_id=rid, ticket_id=tid, new_case_ids=case_ids
                    )
                except Exception as exc:  # noqa: BLE001
                    import logging
                    logging.getLogger("ticket.gate").exception("gate run failed: %s", exc)
                    row = await bg_db.get(EvalRun, rid)
                    ticket = await bg_db.get(ImprovementTicket, tid)
                    if row:
                        row.status = "failed"
                        row.notes = str(exc)[:500]
                    if ticket:
                        ticket.status = "gate_failed"
                        ticket.gate_result = f"FAIL · run error: {exc}"[:500]
                    await bg_db.commit()

        if run_id:
            background_tasks.add_task(_gate_bg, run_id, ticket_id, new_ids)
        return ok(payload)
    except LookupError:
        return fail(404, "ticket not found")
    except ValueError as exc:
        return _ticket_value_error_response(exc)


@router.post("/tickets/{ticket_id}/retest")
async def ticket_retest(
    ticket_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_operate_tickets(normalize_role(user.role)):
        return fail(403, "forbidden")
    try:
        payload = await retest_ticket_gate(db, ticket_id, triggered_by=user.username or TECH_SUPER_ADMIN)
        gate_run = payload.get("gate_run") or {}
        run_id = gate_run.get("run_id")
        new_ids = gate_run.get("new_case_ids") or []

        from src.db.session import AsyncSessionLocal
        from src.eval.runner import finalize_gate_run_for_ticket, run_eval_batch
        from src.models import EvalRun, ImprovementTicket

        async def _gate_bg(rid: int, tid: int, case_ids: list[str]) -> None:
            async with AsyncSessionLocal() as bg_db:
                try:
                    await run_eval_batch(
                        bg_db,
                        run_id=rid,
                        run_type="gate",
                        trigger="ticket_gate",
                        triggered_by=user.username,
                        new_case_ids=case_ids,
                    )
                    await finalize_gate_run_for_ticket(
                        bg_db, run_id=rid, ticket_id=tid, new_case_ids=case_ids
                    )
                except Exception as exc:  # noqa: BLE001
                    import logging
                    logging.getLogger("ticket.gate").exception("gate retest failed: %s", exc)
                    row = await bg_db.get(EvalRun, rid)
                    ticket = await bg_db.get(ImprovementTicket, tid)
                    if row:
                        row.status = "failed"
                    if ticket:
                        ticket.status = "gate_failed"
                    await bg_db.commit()

        if run_id:
            background_tasks.add_task(_gate_bg, run_id, ticket_id, new_ids)
        return ok(payload)
    except LookupError:
        return fail(404, "ticket not found")
    except ValueError as exc:
        return _ticket_value_error_response(exc)


@router.post("/tickets/{ticket_id}/release")
async def ticket_release(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_operate_tickets(normalize_role(user.role)):
        return fail(403, "forbidden")
    try:
        return ok(await confirm_ticket_release(db, ticket_id))
    except LookupError:
        return fail(404, "ticket not found")
    except ValueError as exc:
        return _ticket_value_error_response(exc)


@router.post("/tickets/{ticket_id}/reject")
async def ticket_reject(
    ticket_id: int,
    body: RejectSuggestionRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_operate_tickets(normalize_role(user.role)):
        return fail(403, "仅技术超管可驳回工单")
    try:
        return ok(await reject_suggestion(db, ticket_id, body.reason))
    except LookupError:
        return fail(404, "ticket not found")
    except ValueError as exc:
        return _ticket_value_error_response(exc)


@router.post("/tickets/{ticket_id}/notes")
async def ticket_add_note(
    ticket_id: int,
    body: TicketNoteRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if normalize_role(user.role) != "biz_super_admin":
        return fail(403, "仅业务超管可添加备注")
    try:
        return ok(
            await add_ticket_note(
                db, ticket_id, author=user.username or "unknown", content=body.content
            )
        )
    except LookupError:
        return fail(404, "ticket not found")
    except ValueError as exc:
        return fail(400, str(exc))


@router.post("/tickets/{ticket_id}/withdraw")
async def ticket_withdraw(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if normalize_role(user.role) != "biz_super_admin":
        return fail(403, "仅业务超管可撤回工单")
    try:
        await withdraw_ticket(db, ticket_id, actor_role=user.role)
        return ok({"withdrawn": True, "ticket_id": ticket_id})
    except LookupError:
        return fail(404, "ticket not found")
    except ValueError as exc:
        return fail(400, str(exc))
    except PermissionError as exc:
        return fail(403, str(exc))


@router.post("/tickets/{ticket_id}/defer")
async def ticket_defer(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_review_reports(normalize_role(user.role)):
        return fail(403, "forbidden")
    try:
        return ok(await defer_suggestion(db, ticket_id))
    except LookupError:
        return fail(404, "ticket not found")


@router.get("/payroll/validate-token")
async def validate_token(
    user: CurrentUser = Depends(get_current_user),
    x_payroll_confirm: str | None = Header(None, alias="X-Payroll-Confirm"),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    valid = validate_confirm_token(user.username, x_payroll_confirm)
    return ok({"valid": valid})


# ============ Eval Harness（评测中心） ============
# 规格：仅技术超管可访问（复盘报告才是两个超管都看）

@router.get("/eval/runs")
async def eval_runs_list(
    limit: int = Query(20, ge=1, le=100),
    run_type: str | None = Query(None, description="full | l1_smoke | gate"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_eval_center(normalize_role(user.role)):
        return fail(403, "forbidden")
    items = await list_eval_runs(db, limit=limit, run_type=run_type)
    total = await count_eval_runs(db)
    return ok({"items": items, "total": total})


@router.get("/eval/config")
async def eval_config(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_eval_center(normalize_role(user.role)):
        return fail(403, "forbidden")
    threshold = await resolve_gate_assert_threshold(db)
    return ok({"gate_assert_threshold": threshold, "gate_l1_threshold": threshold})


@router.get("/eval/case-ids")
async def eval_case_ids(
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_operate_tickets(normalize_role(user.role)):
        return fail(403, "forbidden")
    return ok(list_eval_case_ids())


@router.get("/eval/runs/{run_id}")
async def eval_run_detail(
    run_id: int,
    include_cases: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_eval_center(normalize_role(user.role)):
        return fail(403, "forbidden")
    data = await get_eval_run_detail(db, run_id, include_cases=include_cases)
    if not data:
        return fail(404, "eval run not found")
    await attach_run_metrics_from_cases(db, run_id, data)
    return ok(data)


@router.post("/eval/runs/{run_id}/set-baseline")
async def eval_set_baseline(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_operate_tickets(normalize_role(user.role)):
        return fail(403, "仅技术超管可设定基线")
    try:
        payload = await set_eval_baseline(db, run_id)
        await write_audit(
            db,
            actor=user.username,
            action="eval.set_baseline",
            target_id=str(run_id),
            detail={"run_id": run_id},
        )
        return ok(payload)
    except LookupError:
        return fail(404, "eval run not found")
    except ValueError as exc:
        return fail(422, str(exc))


@router.post("/eval/runs")
async def eval_runs_trigger(
    background_tasks: BackgroundTasks,
    only_layer1: bool = Query(False, description="兼容旧参数；等同 run_type=l1_smoke"),
    run_type: str | None = Query(None, description="full | l1_smoke（门禁仅工单触发）"),
    case_limit: int | None = Query(None, ge=1, le=200, description="仅跑前 N 条，测试用"),
    version: str | None = Query(None, description="版本标签，默认 MMDD-HHmm；可传自定义如 v1.4.0"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """触发一次评测跑批。后台异步跑，立即返回 run_id；前端轮询 detail 看进度。"""
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_eval_center(normalize_role(user.role)):
        return fail(403, "forbidden")
    if run_type == "gate":
        return fail(400, "门禁跑批仅能从工单触发")

    rt = run_type or ("l1_smoke" if only_layer1 else "full")

    from src.db.session import AsyncSessionLocal
    from src.eval.runner import create_eval_run, run_eval_batch
    from src.eval.version import normalize_eval_version
    from src.models import EvalRun

    ver = normalize_eval_version(version)
    run_id = await create_eval_run(
        db,
        version=ver,
        trigger="manual",
        triggered_by=user.username,
        case_limit=case_limit,
        run_type=rt,
    )

    async def _run_bg(rid: int) -> None:
        async with AsyncSessionLocal() as bg_db:
            try:
                await run_eval_batch(
                    bg_db,
                    run_id=rid,
                    version=ver,
                    trigger="manual",
                    triggered_by=user.username,
                    run_type=rt,
                    only_layer1=only_layer1,
                    case_limit=case_limit,
                )
            except Exception as exc:  # noqa: BLE001
                import logging
                logging.getLogger("eval.runner").exception("eval batch failed: %s", exc)
                row = await bg_db.get(EvalRun, rid)
                if row:
                    row.status = "failed"
                    row.notes = str(exc)[:500]
                    await bg_db.commit()

    background_tasks.add_task(_run_bg, run_id)
    return ok({
        "run_id": run_id,
        "message": "评测跑批已启动（后台运行）",
        "run_type": rt,
        "only_layer1": only_layer1,
        "case_limit": case_limit,
        "version": ver,
    })


@router.post("/eval/seed-demo")
async def eval_seed_demo(
    body: dict[str, Any] | None = None,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_eval_center(normalize_role(user.role)):
        return fail(403, "forbidden")
    payload = body or {}
    force = bool(payload.get("force"))
    run_ids = await seed_eval_demo(db, force=force)
    return ok({"run_ids": run_ids, "count": len(run_ids), "refreshed": force})


@router.post("/eval/runs/cleanup-garbage")
async def eval_runs_cleanup_garbage(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_eval_center(normalize_role(user.role)):
        return fail(403, "forbidden")
    deleted = await delete_garbage_eval_runs(db)
    return ok({"deleted": deleted})


@router.get("/eval/runs/{run_id}/cases")
async def eval_run_cases(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_eval_center(normalize_role(user.role)):
        return fail(403, "forbidden")
    payload = await list_run_cases(db, run_id)
    if payload is None:
        return fail(404, "eval run not found")
    return ok(payload)


@router.get("/eval/runs/{run_id}/diff")
async def eval_run_diff(
    run_id: int,
    against: int | None = Query(None, description="基线 run_id，默认取上一 done run"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_eval_center(normalize_role(user.role)):
        return fail(403, "forbidden")
    data = await get_run_diff(db, run_id, against=against)
    if not data:
        return fail(404, "eval run not found")
    return ok(data)


@router.get("/eval/coverage")
async def eval_coverage(
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_eval_center(normalize_role(user.role)):
        return fail(403, "forbidden")
    return ok(get_eval_coverage())


@router.post("/eval/feedback")
async def eval_judge_feedback(
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not user.authenticated:
        return fail(401, "请先登录")
    if not can_view_eval_center(normalize_role(user.role)):
        return fail(403, "forbidden")
    try:
        row = await submit_judge_feedback(
            db,
            case_result_id=int(body.get("case_result_id") or 0),
            verdict=str(body.get("verdict") or ""),
            human_overall=body.get("human_overall"),
            note=body.get("note"),
            created_by=user.username or "unknown",
        )
    except LookupError:
        return fail(404, "case result not found")
    except ValueError as exc:
        return fail(400, str(exc))
    return ok(row)
