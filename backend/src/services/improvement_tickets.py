from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

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

TICKET_STATUSES = frozenset({"pending", "in_progress", "awaiting_gate", "released", "rejected", "deferred"})


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
    return {
        "id": row.id,
        "ticket_no": f"#{row.id:03d}",
        "title": row.title,
        "content_biz": row.content_biz,
        "draft_changes": draft,
        "display_body": display_body,
        "content": row.content_biz,
        "source": _format_ticket_source(row),
        "status": row.status,
        "change_target": row.change_target,
        "test_requirement": row.test_requirement,
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
        query = query.where(ImprovementTicket.status == status.strip())
    if mine_only:
        query = query.where(ImprovementTicket.assignee == TECH_SUPER_ADMIN)

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = max(page - 1, 0) * page_size
    result = await db.execute(query.order_by(desc(ImprovementTicket.updated_at)).offset(offset).limit(page_size))
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
        raise ValueError("only pending tickets can be accepted")
    row.status = "in_progress"
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    return _serialize_ticket(row)


async def mark_ticket_done(db: AsyncSession, ticket_id: int) -> dict[str, Any]:
    """技术超管点"我已完成改动 + 已加测试用例" → 自动跑门禁：
       绿 → 进 awaiting_gate 等二次确认；红 → 退回 in_progress 并附失败用例摘要。
    """
    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    if row.status != "in_progress":
        raise ValueError("only in_progress tickets can be marked done")
    row.status = "awaiting_gate"
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    gate = run_router_gate()
    if gate.get("passed"):
        row.gate_result = _format_gate_summary(gate, passed=True)
    else:
        # 门禁红 → 自动退回处理中，附失败用例（SOP §4 红回退要求）
        row.status = "in_progress"
        row.gate_result = _format_gate_summary(gate, passed=False)
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    return {**_serialize_ticket(row), "gate": gate}


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
    """技术超管"确认上线" → 铁律：必须 awaiting_gate 且再跑门禁一次仍绿。

    任何角色（含技术超管本人）不得跳过门禁。门禁红 → 退回 in_progress 且拒绝请求；
    门禁绿 → 状态置 released，并回填关联 finding/suggestion/agent_run 为 fixed。
    """
    row = await db.get(ImprovementTicket, ticket_id)
    if not row:
        raise LookupError("ticket not found")
    if row.status != "awaiting_gate":
        # SOP §6 铁律：不在 awaiting_gate 直接拒绝（如 in_progress / rejected / released 状态都不允许）
        raise ValueError(f"ticket must be in awaiting_gate (current: {row.status})")
    gate = run_router_gate()
    if not gate.get("passed"):
        row.status = "in_progress"
        row.gate_result = _format_gate_summary(gate, passed=False)
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        # 上抛给 endpoint，让前端能弹出"门禁失败，已退回处理中"的提示
        raise ValueError(f"router gate failed: {gate.get('summary')}")
    row.status = "released"
    row.gate_result = _format_gate_summary(gate, passed=True)
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    # 回填关联 finding/suggestion 状态 fixed（mock 内存级）
    _mark_source_fixed(row)
    # 回填关联 agent_run.review_status=fixed
    await _backfill_agent_run_review_status(db, row)
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
    row.status = "rejected"
    row.reject_reason = reason.strip()
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
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


async def seed_demo_tickets(db: AsyncSession) -> None:
    count = await db.scalar(select(func.count()).select_from(ImprovementTicket)) or 0
    if count:
        return
    demos = [
        (
            "让系统能正确回答各部门成本类汇总问题",
            "让系统能正确回答「各部门成本」类汇总问题（解决成本查询被误拒）",
            {"target": "路由总纲 ROUTER §3 aggregate 判定", "action": "补充成本类部门查询边界", "add_test_case": "tests/router_cases.yaml 新增 1 条"},
            "05-27复盘",
            "pending",
        ),
        (
            "让员工询问考勤补卡制度时系统能给出明确指引",
            "让员工询问考勤补卡制度时，系统能给出明确指引",
            {"target": "知识库文档", "action": "补充《考勤补卡管理办法》", "add_test_case": "policy 类用例补 1 条"},
            "05-27复盘",
            "in_progress",
        ),
        (
            "(驳回)归因有误",
            "复盘归因与事实不符，暂不处理",
            None,
            "05-20复盘",
            "rejected",
        ),
    ]
    for title, content_biz, draft, source, status in demos:
        db.add(
            ImprovementTicket(
                title=title,
                content_biz=content_biz,
                draft_changes=draft,
                source=source,
                status=status,
                change_target=(draft or {}).get("target") if draft else None,
                test_requirement=(draft or {}).get("add_test_case") if draft else None,
                assignee=TECH_SUPER_ADMIN,
                reject_reason="归因有误" if status == "rejected" else None,
            )
        )
    await db.commit()


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
