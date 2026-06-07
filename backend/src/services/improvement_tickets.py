from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.eval.case_draft import build_eval_case_yaml_draft
from src.eval.loader import load_eval_set
from src.models import ImprovementTicket, User
from src.services.review_finding_validator import format_draft_changes
from src.services.rbac import (
    BIZ_SUPER_ADMIN,
    STAFF,
    TECH_SUPER_ADMIN,
    can_operate_tickets,
    can_track_tickets,
    normalize_role,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]

TICKET_STATUSES = frozenset({
    "pending",
    "in_progress",
    "gate_running",
    "gate_failed",
    "gate_passed",
    "released",
    "rejected",
    "deferred",
    "awaiting_gate",  # legacy DB status
})

# 显式状态转移白名单（raw DB status → 允许的目标 status）
TICKET_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"in_progress", "rejected"}),
    "in_progress": frozenset({"gate_running"}),
    "gate_running": frozenset({"gate_failed", "gate_passed"}),
    "gate_failed": frozenset({"gate_running"}),
    "gate_passed": frozenset({"released", "gate_running"}),
    "awaiting_gate": frozenset({"gate_running"}),  # legacy 旧流程重新提测
    "released": frozenset(),
    "rejected": frozenset(),
    "deferred": frozenset(),
}


class TicketTransitionError(ValueError):
    """Illegal ticket status transition."""


def _assert_ticket_transition(row: ImprovementTicket, to_status: str) -> None:
    from_st = (row.status or "").strip()
    allowed = TICKET_TRANSITIONS.get(from_st, frozenset())
    if to_status not in allowed:
        hint = "、".join(sorted(allowed)) if allowed else "无"
        raise TicketTransitionError(f"非法状态转移：{from_st} → {to_status}（允许：{hint}）")


def _apply_ticket_status(row: ImprovementTicket, to_status: str) -> None:
    _assert_ticket_transition(row, to_status)
    row.status = to_status
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)


def _format_ticket_source(row: ImprovementTicket) -> str:
    """统一来源展示：优先用 report period，否则规范化 legacy 字符串。"""
    from src.services.review_suggestions import format_review_source

    if row.source_report_id:
        report = next((r for r in MOCK_REVIEW_REPORTS if r.get("id") == row.source_report_id), None)
        if report:
            return format_review_source(period=report.get("period"), week=report.get("week"), label=report.get("label"))
    src = (row.source or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}\s*~\s*\d{4}-\d{2}-\d{2}", src):
        return src if "复盘" in src else f"{src} 复盘"
    return src or "复盘报告"


def _assignee_label(assignee: str | None) -> str:
    if assignee == TECH_SUPER_ADMIN:
        return "技术主管"
    return assignee or "—"


def _is_legacy_gate_ticket(row: ImprovementTicket) -> bool:
    """Old pytest-gate era tickets: awaiting_gate without eval run linkage."""
    if row.linked_run_id:
        return False
    st = (row.status or "").strip()
    return st in {"awaiting_gate", "gate_passed"}


def _normalize_ticket_status(row: ImprovementTicket) -> str:
    st = (row.status or "").strip()
    if _is_legacy_gate_ticket(row):
        return "legacy_retest_pending"
    if st == "awaiting_gate" and row.linked_run_id:
        return "gate_passed"
    return st


def _ticket_no(row: ImprovementTicket) -> str:
    return f"#{row.id:03d}" if row.id is not None else "—"


def _serialize_ticket(row: ImprovementTicket, *, role: str | None = None) -> dict[str, Any]:
    source_link = _resolve_source_link(row, role=role)
    role_n = normalize_role(role) if role else BIZ_SUPER_ADMIN
    draft = row.draft_changes or {}
    tech_body = format_draft_changes(draft)
    if tech_body == "—" and (row.change_target or row.test_requirement):
        parts: list[str] = []
        if row.change_target:
            parts.append(f"改动：{row.change_target}")
        if row.test_requirement:
            parts.append(f"测试：{row.test_requirement}")
        tech_body = " · ".join(parts) if parts else row.content_biz
    display_body = tech_body if role_n == TECH_SUPER_ADMIN else row.content_biz
    st = _normalize_ticket_status(row)
    eval_link = _ticket_eval_link(row)
    source_link = source_link or {}
    eval_yaml_draft = None
    if role_n == TECH_SUPER_ADMIN and st in {"in_progress", "gate_failed"} and row.id is not None:
        eval_yaml_draft = build_eval_case_yaml_draft(
            ticket_id=row.id,
            draft_changes=draft,
            test_requirement=row.test_requirement,
            content_biz=row.content_biz,
            source_phenomenon=(source_link.get("finding") or {}).get("phenomenon"),
        )
    return {
        "id": row.id,
        "ticket_no": _ticket_no(row),
        "title": row.title,
        "content_biz": row.content_biz,
        "draft_changes": draft,
        "display_body": display_body,
        "content_formatted": _format_ticket_content(row),
        "content": row.content_biz,
        "source": _format_ticket_source(row),
        "status": st,
        "raw_status": row.status,
        "is_legacy_gate": _is_legacy_gate_ticket(row),
        "change_target": row.change_target,
        "test_requirement": row.test_requirement,
        "new_case_ids": list(row.new_case_ids or []),
        "eval_case_yaml_draft": eval_yaml_draft,
        "linked_run_id": row.linked_run_id,
        "eval_link": eval_link,
        "evidence_run_ids": (row.evidence_run_ids or "").split(",") if row.evidence_run_ids else [],
        "reject_reason": row.reject_reason,
        "gate_result": row.gate_result,
        "assignee": row.assignee,
        "assignee_label": _assignee_label(row.assignee),
        "source_type": row.source_type,
        "source_report_id": row.source_report_id,
        "source_finding_id": row.source_finding_id,
        "source_suggestion_id": row.source_suggestion_id,
        "source_link": source_link,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "notes": list(TICKET_NOTES.get(row.id, [])),
    }


def _format_ticket_content(row: ImprovementTicket) -> str:
    parts: list[str] = []
    if row.change_target:
        parts.append(f"改动：{row.change_target}")
    ids = list(row.new_case_ids or [])
    if ids:
        intent_hint = row.test_requirement or "用例"
        parts.append(f"用例：{intent_hint} +{len(ids)}（{', '.join(ids)}）")
    elif row.test_requirement:
        parts.append(f"用例：{row.test_requirement}")
    return " · ".join(parts) if parts else row.content_biz


def _ticket_eval_summary(row: ImprovementTicket) -> tuple[str, str]:
    """Return (label_suffix, filter) for eval center deep link."""
    rid = row.linked_run_id
    if row.status == "gate_running":
        return ("跑批中", "all")
    if row.status == "gate_failed":
        return ("未通过", "all")
    if row.status in {"gate_passed", "released"}:
        return ("全绿" if row.status == "gate_passed" else "已上线", "all")
    summary = (row.gate_result or "").upper()
    if "FAIL" in summary:
        return ("未通过", "all")
    if "PASS" in summary or "RELEASED" in summary:
        return ("全绿", "all")
    return ("查看", "all")


def _ticket_eval_link(row: ImprovementTicket) -> dict[str, Any] | None:
    if not row.linked_run_id:
        return None
    suffix, filter_key = _ticket_eval_summary(row)
    return {
        "run_id": row.linked_run_id,
        "label": f"Run #{row.linked_run_id} · {suffix}",
        "filter": filter_key,
    }


def _validate_new_case_ids(new_case_ids: list[str]) -> None:
    if not new_case_ids:
        raise ValueError("工单未声明评测用例，请先将用例入集并登记")
    known = {c["id"] for c in load_eval_set()}
    missing = [cid for cid in new_case_ids if cid not in known]
    if missing:
        raise ValueError(f"以下用例 id 不在评测集中：{', '.join(missing)}")


async def trigger_gate_run(
    db: AsyncSession,
    ticket_id: int,
    *,
    new_case_ids: list[str] | None = None,
    triggered_by: str = TECH_SUPER_ADMIN,
) -> dict[str, Any]:
    """Start gate eval run for ticket (sync setup; batch runs in background)."""
    from src.eval.baseline import get_released_baseline_run_id
    from src.eval.runner import create_eval_run

    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    if row.status == "gate_running":
        raise ValueError("门禁跑批进行中，请等待完成")

    case_ids = list(new_case_ids or row.new_case_ids or [])
    _validate_new_case_ids(case_ids)
    row.new_case_ids = case_ids

    baseline_run_id = await get_released_baseline_run_id(db)
    _apply_ticket_status(row, "gate_running")
    await db.commit()

    run_id = await create_eval_run(
        db,
        version=f"gate-工单#{row.id:03d}",
        trigger="ticket_gate",
        triggered_by=triggered_by,
        run_type="gate",
        source_ticket_id=row.id,
        baseline_run_id=baseline_run_id,
    )
    row.linked_run_id = run_id
    await db.commit()
    return {"ticket_id": row.id, "run_id": run_id, "new_case_ids": case_ids}


async def update_ticket_new_case_ids(
    db: AsyncSession,
    ticket_id: int,
    new_case_ids: list[str],
) -> dict[str, Any]:
    """Register eval case ids on ticket (DB only — eval_set.yaml is edited via Git)."""
    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    if row.status not in {"in_progress", "gate_failed"}:
        raise ValueError("仅处理中或门禁失败工单可登记评测用例")
    ids = list(dict.fromkeys(x.strip() for x in new_case_ids if x and str(x).strip()))
    if ids:
        known = {c["id"] for c in load_eval_set()}
        missing = [cid for cid in ids if cid not in known]
        if missing:
            raise ValueError(f"以下用例 id 不在评测集中：{', '.join(missing)}")
    row.new_case_ids = ids or None
    await db.commit()
    return _serialize_ticket(row, role=TECH_SUPER_ADMIN)


async def mark_ticket_done(
    db: AsyncSession,
    ticket_id: int,
    *,
    new_case_ids: list[str] | None = None,
    triggered_by: str = TECH_SUPER_ADMIN,
) -> dict[str, Any]:
    """标记完成 · 复跑门禁（异步 gate run）。"""
    payload = await trigger_gate_run(
        db, ticket_id, new_case_ids=new_case_ids, triggered_by=triggered_by
    )
    row = await db.get(ImprovementTicket, ticket_id)
    return {**_serialize_ticket(row), "gate_run": payload}


async def retest_ticket_gate(
    db: AsyncSession,
    ticket_id: int,
    *,
    triggered_by: str = TECH_SUPER_ADMIN,
) -> dict[str, Any]:
    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    if row.status == "gate_failed":
        return await mark_ticket_done(db, ticket_id, triggered_by=triggered_by)
    if _is_legacy_gate_ticket(row) or row.status == "awaiting_gate":
        return await mark_ticket_done(db, ticket_id, triggered_by=triggered_by)
    raise ValueError("only gate_failed or legacy awaiting tickets can retest")


def _resolve_source_link(row: ImprovementTicket, *, role: str | None = None) -> dict[str, Any] | None:
    """根据 source_*_id 反查 mock 复盘报告，返回详情页可展示的 finding/suggestion 概要。

    返回字段：
      - report_label / report_period
      - finding (id/text/hypothesis/run_count/run_ids) 若 finding_id 有效
      - suggestion (id/title/change_target/test_requirement) 若 suggestion_id 有效
    """
    if row.source_type != "review_report" or not row.source_report_id:
        return None
    report = next((r for r in MOCK_REVIEW_REPORTS if r.get("id") == row.source_report_id), None)
    if not report:
        return None
    link: dict[str, Any] = {
        "report_id": report.get("id"),
        "report_label": report.get("label"),
        "report_period": report.get("period"),
        "report_week": report.get("week"),
    }
    if row.source_finding_id:
        finding = next(
            (f for f in (report.get("findings") or []) if f.get("id") == row.source_finding_id),
            None,
        )
        if finding:
            link["finding"] = {
                "id": finding["id"],
                "biz_problem": finding.get("biz_problem"),
                "impact": finding.get("impact"),
                "priority": finding.get("priority"),
                "phenomenon": finding.get("phenomenon"),
                "root_cause_hypothesis": finding.get("root_cause_hypothesis"),
                "kind": finding.get("kind"),
                "run_count": finding.get("run_count"),
                "run_ids": finding.get("evidence_run_ids") or finding.get("run_ids") or [],
                "status": finding.get("status", "open"),
            }
    if row.source_suggestion_id:
        suggestion = next(
            (s for s in (report.get("suggestions") or []) if s.get("id") == row.source_suggestion_id),
            None,
        )
        if suggestion:
            from src.services.review_suggestions import normalize_suggestion_modules

            norm = normalize_suggestion_modules(suggestion)
            role_n = normalize_role(role) if role else BIZ_SUPER_ADMIN
            link["suggestion"] = {
                "id": suggestion["id"],
                "content_biz": norm.get("content_biz"),
                "draft_changes": norm.get("draft_changes"),
                "status": suggestion.get("status", "open"),
                "ticket_id": suggestion.get("ticket_id"),
            }
            if role_n == TECH_SUPER_ADMIN:
                link["suggestion"].pop("content_biz", None)
            else:
                link["suggestion"].pop("draft_changes", None)
    return link


async def list_tickets(
    db: AsyncSession,
    *,
    role: str,
    status: str | None = None,
    mine_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    if not can_track_tickets(role) and not (mine_only and can_operate_tickets(role)):
        return {"items": [], "total": 0, "pagination": {"page": page, "page_size": page_size, "total": 0}}

    query = select(ImprovementTicket)
    if status:
        st = status.strip()
        if st in {"legacy_retest_pending", "awaiting_gate"}:
            query = query.where(
                ImprovementTicket.linked_run_id.is_(None),
                ImprovementTicket.status.in_(("awaiting_gate", "gate_passed")),
            )
        else:
            query = query.where(ImprovementTicket.status == st)
    if mine_only:
        query = query.where(ImprovementTicket.assignee == TECH_SUPER_ADMIN)

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = max(page - 1, 0) * page_size
    result = await db.execute(query.order_by(desc(ImprovementTicket.created_at)).offset(offset).limit(page_size))
    return {
        "items": [_serialize_ticket(row, role=role) for row in result.scalars().all()],
        "total": total,
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


async def get_ticket(db: AsyncSession, ticket_id: int, *, role: str | None = None) -> dict[str, Any] | None:
    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        return None
    return _serialize_ticket(row, role=role)


async def create_ticket_from_suggestion(
    db: AsyncSession,
    *,
    title: str,
    content_biz: str,
    source: str,
    draft_changes: dict[str, Any] | None = None,
    change_target: str | None = None,
    test_requirement: str | None = None,
    evidence_run_ids: list[str] | None = None,
    source_type: str = "manual",
    source_report_id: str | None = None,
    source_finding_id: str | None = None,
    source_suggestion_id: str | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    from src.services.review_suggestions import format_review_source

    normalized_source = source.strip()
    if source_report_id:
        report = next((r for r in MOCK_REVIEW_REPORTS if r.get("id") == source_report_id), None)
        if report:
            normalized_source = format_review_source(
                period=report.get("period"), week=report.get("week"), label=report.get("label")
            )

    draft = dict(draft_changes or {})
    resolved_target = change_target or draft.get("target")
    resolved_test = test_requirement or draft.get("add_test_case")

    row = ImprovementTicket(
        title=title.strip(),
        content_biz=content_biz.strip(),
        draft_changes=draft or None,
        source=normalized_source,
        status="pending",
        change_target=resolved_target,
        test_requirement=resolved_test,
        evidence_run_ids=",".join(evidence_run_ids or []),
        assignee=TECH_SUPER_ADMIN,
        source_type=source_type,
        source_report_id=source_report_id,
        source_finding_id=source_finding_id,
        source_suggestion_id=source_suggestion_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    # mock 报告 in-memory 双向回填：suggestion 上记录 ticket_id，方便复盘页显示"已生成工单 #003"
    if source_type == "review_report" and source_report_id and source_suggestion_id:
        from src.services.review_suggestions import mark_suggestion_accepted

        mark_suggestion_accepted(source_report_id, source_suggestion_id, ticket_id=row.id)
    return _serialize_ticket(row, role=role)




def _mark_source_fixed(row: ImprovementTicket) -> None:
    """工单上线时，把对应 finding/suggestion 的 status 置为 fixed（mock 内存级回填）。"""
    if row.source_type != "review_report" or not row.source_report_id:
        return
    report = next((r for r in MOCK_REVIEW_REPORTS if r.get("id") == row.source_report_id), None)
    if not report:
        return
    if row.source_finding_id:
        for finding in report.get("findings") or []:
            if finding.get("id") == row.source_finding_id:
                finding["status"] = "fixed"
                finding["fixed_by_ticket_id"] = row.id
                break
    if row.source_suggestion_id:
        for sug in report.get("suggestions") or []:
            if sug.get("id") == row.source_suggestion_id:
                sug["ticket_released"] = True
                if sug.get("status") not in ("rejected", "hold"):
                    sug.setdefault("status", "accepted")
                sug["ticket_id"] = row.id
                break


async def accept_ticket(db: AsyncSession, ticket_id: int) -> dict[str, Any]:
    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    if row.status != "pending":
        raise TicketTransitionError("仅待处理工单可接单")
    _apply_ticket_status(row, "in_progress")
    await db.commit()
    return _serialize_ticket(row)


def _format_gate_summary(gate: dict[str, Any], *, passed: bool) -> str:
    """把 gate 结果格式化为工单可保存的人类可读摘要（含失败用例片段）。"""
    if passed:
        return f"PASS · {gate.get('summary', 'router_cases.yaml all green')} · @{_now_iso_short()}"
    failures = gate.get("failed_cases") or []
    head = gate.get("summary") or "FAIL"
    if failures:
        cases_repr = "; ".join(failures[:5])
        return f"FAIL @{_now_iso_short()} · {head} · 失败用例: {cases_repr}"
    return f"FAIL @{_now_iso_short()} · {head}"


def _now_iso_short() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def run_router_gate() -> dict[str, Any]:
    """跑 pytest 路由门禁（SOP §6 铁律入口）。

    返回 {passed, summary, failed_cases[], output}。
    failed_cases 是从 pytest 输出里抽出的失败用例标识，供工单展示和回退附用例。
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_router.py", "-m", "offline", "-q"],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    passed = proc.returncode == 0
    summary = "PASS" if passed else "FAIL"
    failed_cases: list[str] = []
    if not passed:
        for line in output.splitlines():
            if "FAILED" in line:
                if summary == "FAIL":
                    summary = line.strip()
                # 抽 "tests/test_router.py::test_router_offline[case-id]" 中括号里的 case id
                if "[" in line and "]" in line:
                    case_id = line.split("[", 1)[1].split("]", 1)[0]
                    failed_cases.append(case_id)
    return {
        "passed": passed,
        "summary": summary,
        "failed_cases": failed_cases,
        "output": output[-4000:],
    }


async def confirm_ticket_release(db: AsyncSession, ticket_id: int) -> dict[str, Any]:
    """确认上线：乐观锁校验版本锚，通过后前移 released baseline。"""
    from src.eval.baseline import set_released_baseline_run_id
    from src.eval.set_version import get_eval_set_version, get_pipeline_version

    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    st = row.status
    if st not in {"gate_passed", "awaiting_gate"}:
        raise ValueError(f"ticket must be gate_passed (current: {st})")
    if not row.linked_run_id or not row.gate_eval_set_version or not row.gate_pipeline_version:
        raise ValueError("该工单未经过评测门禁，请先重新提测")

    current_eval = get_eval_set_version()
    current_pipe = get_pipeline_version()
    if row.gate_eval_set_version and row.gate_eval_set_version != current_eval:
        raise ValueError("环境已变更（评测集版本不一致），请重新提测")
    if row.gate_pipeline_version and row.gate_pipeline_version != current_pipe:
        raise ValueError("环境已变更（主链路版本不一致），请重新提测")
    if not row.linked_run_id:
        raise ValueError("无关联门禁 run，请重新提测")

    # legacy awaiting_gate + 完整门禁锚点 → 按 gate_passed 放行
    if st == "awaiting_gate":
        row.status = "gate_passed"

    _apply_ticket_status(row, "released")
    row.gate_result = f"RELEASED · Run #{row.linked_run_id} · @{_now_iso_short()}"
    _mark_source_fixed(row)
    await _backfill_agent_run_review_status(db, row)
    await set_released_baseline_run_id(db, row.linked_run_id)
    await db.commit()
    return _serialize_ticket(row)


async def _backfill_agent_run_review_status(db: AsyncSession, row: ImprovementTicket) -> None:
    """工单上线 → 关联 evidence_run_ids 对应的 agent_run 全部置 review_status='fixed'。

    evidence_run_ids 既可能是真实 UUID（线上 agent_run.id），也可能是 mock 的 'run-w22-m1'
    形式。后者无法转 UUID，跳过即可，不影响流程。
    """
    import uuid as _uuid
    run_ids_raw = [r.strip() for r in (row.evidence_run_ids or "").split(",") if r.strip()]
    if not run_ids_raw:
        return
    parsed: list[_uuid.UUID] = []
    skipped: list[str] = []
    for rid in run_ids_raw:
        try:
            parsed.append(_uuid.UUID(rid))
        except (ValueError, TypeError):
            skipped.append(rid)
    if not parsed:
        return  # 全是 mock 假 id，无需 update

    from src.models import AgentRun  # 延迟导入避免循环依赖
    from sqlalchemy import update

    try:
        await db.execute(
            update(AgentRun)
            .where(AgentRun.id.in_(parsed))
            .values(review_status="fixed")
        )
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("ticket.release").warning(
            "backfill agent_run.review_status failed for run_ids=%s: %s", parsed, exc,
        )


async def reject_suggestion(db: AsyncSession, ticket_id: int, reason: str) -> dict[str, Any]:
    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    if row.status != "pending":
        raise TicketTransitionError("仅待处理工单可驳回")
    _apply_ticket_status(row, "rejected")
    row.reject_reason = reason.strip()
    await db.commit()
    return _serialize_ticket(row)


async def defer_suggestion(db: AsyncSession, ticket_id: int) -> dict[str, Any]:
    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    row.status = "deferred"
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    return _serialize_ticket(row)


# 工单备注（mock 内存；生产可落 ticket_note 表）
TICKET_NOTES: dict[int, list[dict[str, Any]]] = {}


def _append_ticket_note(ticket_id: int, *, author: str, content: str) -> dict[str, Any]:
    entry = {
        "author": author,
        "author_label": author,
        "content": content.strip(),
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }
    TICKET_NOTES.setdefault(ticket_id, []).append(entry)
    return entry


async def add_ticket_note(
    db: AsyncSession,
    ticket_id: int,
    *,
    author: str,
    content: str,
) -> dict[str, Any]:
    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    text = content.strip()
    if not text:
        raise ValueError("note content required")
    _append_ticket_note(ticket_id, author=author, content=text)
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    return _serialize_ticket(row)


async def withdraw_ticket(
    db: AsyncSession,
    ticket_id: int,
    *,
    actor_role: str,
) -> None:
    from src.services.rbac import normalize_role

    if normalize_role(actor_role) != "biz_super_admin":
        raise PermissionError("only biz_super_admin can withdraw tickets")
    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    if row.status != "pending":
        raise ValueError("only pending tickets can be withdrawn")
    await db.delete(row)
    await db.commit()
    TICKET_NOTES.pop(ticket_id, None)


# Mock 数据：复盘 Agent 每周生成一份报告，按时间倒序排列。
# 真实环境中由复盘 Agent 写入 review_reports 表，本处仅用于前端 demo。
MOCK_REVIEW_REPORTS: list[dict[str, Any]] = [
    {
        "id": "r-2026-w22",
        "week": "2026-W22",
        "period": "2026-05-27 ~ 2026-06-03",
        "label": "最新一周 (5/27-6/3)",
        "generated_at": "2026-06-03T09:00:00",
        "metrics": {
            "total_qa": 1342,
            "down_rate": 0.058,
            "timeout_rate": 0.009,
            "rag_zero_rate": 0.072,
            "intent_distribution": {"aggregate": 0.34, "policy": 0.19, "attribution": 0.22},
            "badcase_reasons": {"rag_zero_hit": 0.38, "clarify": 0.31, "user_down": 0.22, "timeout": 0.09},
        },
        "findings": [
            {
                "id": "f1-w22",
                "finding_key": "F1",
                "kind": "fact",
                "biz_problem": "员工咨询「年终奖怎么核算」时，系统经常无法给出有效答复",
                "impact": "本周 15 次，员工拿不到明确答案",
                "priority": "high",
                "phenomenon": "用户问年终奖核算口径类问题，检索未命中制度片段，无法引用文档作答",
                "root_cause_hypothesis": "[推测] 知识库缺《年终奖核算管理办法》或索引未覆盖相关表述",
                "node_clues": "retriever 节点 chunks_hit=0；document 节点未加载到有效片段",
                "evidence_run_ids": ["run-w22-m1", "run-w22-m2"],
                "run_count": 15,
                "run_ids": ["run-w22-m1", "run-w22-m2"],
                "category": "data",
            },
            {
                "id": "f2-w22",
                "finding_key": "F2",
                "kind": "fact",
                "biz_problem": "员工查询「各部门成本」汇总时，常被系统当作个人薪资问题拒绝回答",
                "impact": "本周 6 次，部门级成本分析无法完成",
                "priority": "high",
                "phenomenon": "用户问部门成本类聚合问题，guardrail 判定 payroll_sensitive=true 直接拒答",
                "root_cause_hypothesis": "[推测] Planner 将「成本」与薪资敏感词绑定过严，aggregate 意图未生效",
                "node_clues": "Planner payroll_sensitive=true → guardrail 拦截；未进入 aggregate 子图",
                "evidence_run_ids": ["run-w22-c1"],
                "run_count": 6,
                "run_ids": ["run-w22-c1"],
                "category": "routing",
            },
        ],
        "suggestions": [
            {
                "id": "s1-w22",
                "content_biz": "让员工咨询年终奖核算规则时，系统能给出明确答复",
                "draft_changes": {
                    "target": "知识库文档",
                    "action": "补充《年终奖核算管理办法》",
                    "add_test_case": "policy 类用例补 1 条",
                },
                "evidence_run_ids": ["run-w22-m1", "run-w22-m2"],
            },
            {
                "id": "s2-w22",
                "content_biz": "让系统能正确回答「人均成本」类部门汇总问题",
                "draft_changes": {
                    "target": "PLANNER_FEW_SHOT",
                    "action": "增加人均类聚合示例",
                    "add_test_case": "tests/router_cases.yaml 新增 1 条",
                },
                "evidence_run_ids": ["run-w22-c1"],
            },
        ],
    },
    {
        "id": "r-2026-w21",
        "week": "2026-W21",
        "period": "2026-05-20 ~ 2026-05-27",
        "label": "2026 第21周 (5/20-5/27)",
        "generated_at": "2026-05-27T09:00:00",
        "metrics": {
            "total_qa": 1240,
            "down_rate": 0.062,
            "timeout_rate": 0.011,
            "rag_zero_rate": 0.08,
            "intent_distribution": {"aggregate": 0.32, "policy": 0.21, "attribution": 0.18},
            "badcase_reasons": {"rag_zero_hit": 0.42, "clarify": 0.28, "user_down": 0.2, "timeout": 0.1},
        },
        "findings": [
            {
                "id": "f1-w21",
                "finding_key": "F3",
                "kind": "fact",
                "biz_problem": "员工询问「考勤补卡」相关制度时，系统多次无法提供有效指引",
                "impact": "本周 12 次，制度类问题得不到解答",
                "priority": "high",
                "phenomenon": "考勤补卡类 policy 提问，RAG 检索 0 命中，回答为空或泛化拒答",
                "root_cause_hypothesis": "[推测] 知识库未收录《考勤补卡管理办法》或未建立索引",
                "node_clues": "retriever chunks_hit=0；policy skill 未加载制度文档",
                "evidence_run_ids": ["run-m1", "run-m2"],
                "run_count": 12,
                "run_ids": ["run-m1", "run-m2"],
                "category": "data",
            },
            {
                "id": "f2-w21",
                "finding_key": "F4",
                "kind": "fact",
                "biz_problem": "员工查询「各部门成本」汇总时，常被系统当作个人薪资问题拒绝回答",
                "impact": "本周 8 次，部门级成本分析无法完成",
                "priority": "high",
                "phenomenon": "含「成本」的部门级 aggregate 提问被 guardrail 拦截",
                "root_cause_hypothesis": "[推测] ROUTER aggregate 边界未覆盖「成本类部门查询」",
                "node_clues": "Planner → guardrail reject；aggregate 子图未触发",
                "evidence_run_ids": ["run-c1", "run-c2"],
                "run_count": 8,
                "run_ids": ["run-c1", "run-c2"],
                "category": "routing",
            },
        ],
        "suggestions": [
            {
                "id": "s1-w21",
                "content_biz": "让员工询问考勤补卡制度时，系统能给出明确指引",
                "draft_changes": {
                    "target": "知识库文档",
                    "action": "补充《考勤补卡管理办法》",
                    "add_test_case": "policy 类用例补 1 条",
                },
                "evidence_run_ids": ["run-m1", "run-m2"],
            },
            {
                "id": "s2-w21",
                "content_biz": "让系统能正确回答「各部门成本」类汇总问题（解决成本查询被误拒）",
                "draft_changes": {
                    "target": "路由总纲 ROUTER §3 aggregate 判定",
                    "action": "补充成本类部门查询边界 few-shot",
                    "add_test_case": "tests/router_cases.yaml 新增 1 条",
                },
                "evidence_run_ids": ["run-c1", "run-c2"],
            },
        ],
    },
    {
        "id": "r-2026-w20",
        "week": "2026-W20",
        "period": "2026-05-13 ~ 2026-05-20",
        "label": "2026 第20周 (5/13-5/20)",
        "generated_at": "2026-05-20T09:00:00",
        "metrics": {
            "total_qa": 1108,
            "down_rate": 0.071,
            "timeout_rate": 0.015,
            "rag_zero_rate": 0.094,
            "intent_distribution": {"aggregate": 0.29, "policy": 0.24, "attribution": 0.16},
            "badcase_reasons": {"rag_zero_hit": 0.46, "clarify": 0.24, "user_down": 0.18, "timeout": 0.12},
        },
        "findings": [
            {
                "id": "f1-w20",
                "kind": "fact",
                "text": "9 例归因任务超时，集中在「离职原因」深度分析",
                "hypothesis": "归因子图节点过多，建议拆分或增加并行度",
                "run_count": 9,
                "run_ids": ["run-w20-t1"],
            },
        ],
        "suggestions": [
            {
                "id": "s1-w20",
                "content_biz": "让员工询问离职原因深度分析时，系统能在合理时间内给出结论",
                "draft_changes": {
                    "target": "harness 配置",
                    "action": "归因 Agent 子图并行度调整",
                    "add_test_case": "tests/attribution_perf.py 添加 1 条",
                },
                "evidence_run_ids": ["run-w20-t1"],
            },
        ],
    },
    {
        "id": "r-2026-w19",
        "week": "2026-W19",
        "period": "2026-05-06 ~ 2026-05-13",
        "label": "2026 第19周 (5/6-5/13)",
        "generated_at": "2026-05-13T09:00:00",
        "metrics": {
            "total_qa": 985,
            "down_rate": 0.083,
            "timeout_rate": 0.018,
            "rag_zero_rate": 0.11,
            "intent_distribution": {"aggregate": 0.28, "policy": 0.26, "attribution": 0.14},
            "badcase_reasons": {"rag_zero_hit": 0.51, "clarify": 0.22, "user_down": 0.17, "timeout": 0.10},
        },
        "findings": [
            {
                "id": "f1-w19",
                "kind": "fact",
                "text": "7 例 clarify 二次澄清后用户放弃",
                "hypothesis": "澄清选项太多或问法引导不清晰",
                "run_count": 7,
                "run_ids": ["run-w19-q1"],
            },
        ],
        "suggestions": [
            {
                "id": "s1-w19",
                "content_biz": "让员工在需要澄清身份或问题时，系统引导更清晰、选项更少",
                "draft_changes": {
                    "target": "clarify_helpers.build_employee_clarify",
                    "action": "Clarify 文案优化（限制 3 个候选）",
                    "add_test_case": "前端 UX 检查 + 抽样回放",
                },
                "evidence_run_ids": ["run-w19-q1"],
            },
        ],
    },
]

# 向后兼容旧的单份引用（如 admin.py 里取 period 拼工单 source）
MOCK_REVIEW_REPORT = MOCK_REVIEW_REPORTS[1] if len(MOCK_REVIEW_REPORTS) > 1 else MOCK_REVIEW_REPORTS[0]


def list_mock_review_reports(week: str | None = None, *, role: str | None = None) -> list[dict[str, Any]]:
    """返回 mock 报告列表，支持按周筛选。

    week:
      - None / 空 / 'all'  → 返回全部报告（默认）
      - 'latest'           → 返回最新一份
      - 具体周值如 '2026-W21' → 仅返回该周
    """
    from src.services.review_suggestions import enrich_review_report, seed_demo_suggestion_states

    seed_demo_suggestion_states()
    if not week or week == "all":
        return [enrich_review_report(dict(r), role=role) for r in MOCK_REVIEW_REPORTS]
    if week == "latest":
        return (
            [enrich_review_report(dict(MOCK_REVIEW_REPORTS[0]), role=role)]
            if MOCK_REVIEW_REPORTS
            else []
        )
    return [
        enrich_review_report(dict(r), role=role)
        for r in MOCK_REVIEW_REPORTS
        if r.get("week") == week
    ]


def list_mock_review_periods() -> list[dict[str, str]]:
    """返回可用周期列表（按时间倒序），供前端筛选下拉用。"""
    return [
        {"value": r["week"], "label": r["label"], "period": r["period"]}
        for r in MOCK_REVIEW_REPORTS
    ]


# Fresh-clone demo tickets (one per workflow state). Wired to eval gate runs in demo_seed.
DEMO_TICKET_TITLES = {
    "pending": "【演示】待处理·考勤补卡制度指引",
    "in_progress": "【演示】处理中·各部门成本汇总",
    "gate_failed": "【演示】门禁未通过·人均成本汇总",
    "gate_passed": "【演示】门禁通过·年终奖核算",
    "released": "【演示】已上线·路由聚合边界",
}


async def seed_demo_tickets(db: AsyncSession) -> int:
    """幂等补种演示工单：覆盖各状态各 1 张，按 title 缺失则插入。"""
    demos = [
        (
            DEMO_TICKET_TITLES["pending"],
            "让员工询问考勤补卡制度时，系统能给出明确指引",
            {"target": "知识库文档", "action": "补充《考勤补卡管理办法》", "add_test_case": "policy 类用例 +1"},
            "05-27复盘",
            "pending",
            None,
        ),
        (
            DEMO_TICKET_TITLES["in_progress"],
            "让系统能正确回答「各部门成本」类汇总问题（解决成本查询被误拒）",
            {"target": "路由总纲 ROUTER §3 aggregate 判定", "action": "补充成本类部门查询边界", "add_test_case": "aggregate 类用例 +1"},
            "05-27复盘",
            "in_progress",
            None,
        ),
        (
            DEMO_TICKET_TITLES["gate_failed"],
            "让系统能正确回答「人均成本」类部门汇总问题",
            {"target": "PLANNER_FEW_SHOT", "action": "增加人均类聚合示例", "add_test_case": "aggregate 类用例 +1"},
            "05-27复盘",
            "gate_failed",
            None,
        ),
        (
            DEMO_TICKET_TITLES["gate_passed"],
            "让员工咨询年终奖核算规则时，系统能给出明确答复",
            {"target": "知识库文档", "action": "补充《年终奖核算管理办法》", "add_test_case": "policy 类用例 +1"},
            "05-27复盘",
            "gate_passed",
            None,
        ),
        (
            DEMO_TICKET_TITLES["released"],
            "让系统能正确回答各部门成本类汇总问题",
            {"target": "路由总纲 ROUTER §3 aggregate 判定", "action": "补充成本类部门查询边界", "add_test_case": "aggregate 类用例 +1"},
            "05-20复盘",
            "released",
            None,
        ),
    ]
    inserted = 0
    for title, content_biz, draft, source, status, new_ids in demos:
        exists = await db.scalar(
            select(ImprovementTicket.id).where(ImprovementTicket.title == title).limit(1)
        )
        if exists:
            continue
        db.add(
            ImprovementTicket(
                title=title,
                content_biz=content_biz,
                draft_changes=draft,
                source=source,
                status=status,
                change_target=(draft or {}).get("target") if draft else None,
                test_requirement=(draft or {}).get("add_test_case") if draft else None,
                new_case_ids=new_ids,
                assignee=TECH_SUPER_ADMIN,
            )
        )
        inserted += 1
    if inserted:
        await db.commit()
    return inserted


async def seed_demo_users(db: AsyncSession, pwd_hash_fn) -> None:
    """新规格演示账号：
    - tech_admin: 技术超管，永久无薪资权
    - biz_hrd: 业务超管，岗位自带薪资权
    - staff1: 普通员工，永久薪资隔离
    
    payroll_access 字段保留用于向后兼容，但实际权限只看角色。
    """
    demos = [
        ("tech_admin", "tech123", TECH_SUPER_ADMIN, "开发者", "ADM001", False, None),
        ("biz_hrd", "hrd123", BIZ_SUPER_ADMIN, "张HRD", "HR0001", True, "tech_admin"),  # 业务超管自带薪资权
        ("staff1", "staff123", STAFF, "陈某", "E12099", False, "biz_hrd"),  # 普通员工无薪资权
    ]
    for username, password, role, display_name, employee_id, payroll, created_by in demos:
        user = await db.scalar(select(User).where(User.username == username))
        if user:
            # 更新现有用户角色和薪资权（确保与新规格一致）
            user.role = role
            user.payroll_access = payroll
            continue
        db.add(
            User(
                username=username,
                password_hash=pwd_hash_fn(password),
                role=role,
                display_name=display_name,
                employee_id=employee_id,
                payroll_access=payroll,
                created_by=created_by,
            )
        )
    await db.commit()
