"""复盘报告建议状态（mock 内存态）— 采纳 / 驳回 / 存疑闭环。

真实环境应落 review_suggestion 表；本阶段与 MOCK_REVIEW_REPORTS 同址更新，便于演示。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from src.services.improvement_tickets import MOCK_REVIEW_REPORTS
from src.services.rbac import BIZ_SUPER_ADMIN, TECH_SUPER_ADMIN, normalize_role
from src.services.review_finding_validator import (
    format_draft_changes,
    validate_biz_problem,
    validate_content_biz,
)

SUGGESTION_PENDING = "pending"
SUGGESTION_ACCEPTED = "accepted"
SUGGESTION_REJECTED = "rejected"
SUGGESTION_HOLD = "hold"


def format_review_source(*, period: str | None = None, week: str | None = None, label: str | None = None) -> str:
    """统一工单来源格式：「2026-05-20 ~ 2026-05-27 复盘」。"""
    if period and period.strip():
        p = period.strip()
        if "复盘" not in p:
            return f"{p} 复盘"
        return p
    if label and label.strip():
        return f"{label.strip()} 复盘"
    if week and week.strip():
        return f"{week.strip()} 复盘"
    return "复盘报告"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _ensure_suggestion_defaults(report: dict[str, Any]) -> None:
    for sug in report.get("suggestions") or []:
        sug.setdefault("status", SUGGESTION_PENDING)


def _find_suggestion(suggestion_id: str, report_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    reports = MOCK_REVIEW_REPORTS
    if report_id:
        reports = [r for r in MOCK_REVIEW_REPORTS if r.get("id") == report_id] or MOCK_REVIEW_REPORTS
    for report in reports:
        _ensure_suggestion_defaults(report)
        for sug in report.get("suggestions") or []:
            if sug.get("id") == suggestion_id:
                return report, sug, dict(sug)
    return None


def _text_similarity(a: str, b: str) -> float:
    a = re.sub(r"\s+", "", (a or "").lower())
    b = re.sub(r"\s+", "", (b or "").lower())
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def normalize_finding_modules(finding: dict[str, Any]) -> dict[str, Any]:
    """A 方案：补齐模块 A/B 字段；校验 biz_problem 人话质量。"""
    fc = dict(finding)
    run_ids = list(fc.get("evidence_run_ids") or fc.get("run_ids") or [])
    fc["evidence_run_ids"] = run_ids
    fc["run_ids"] = run_ids
    fc.setdefault("run_count", len(run_ids))

    if not fc.get("biz_problem"):
        legacy = (fc.get("text") or "").strip()
        fc["biz_problem"] = legacy or "系统在该类问题上表现异常，需进一步分析"
    if not fc.get("phenomenon"):
        fc["phenomenon"] = (fc.get("text") or fc.get("biz_problem") or "").strip()
    if not fc.get("root_cause_hypothesis"):
        hyp = (fc.get("hypothesis") or "").strip()
        fc["root_cause_hypothesis"] = hyp if hyp.startswith("[推测]") else f"[推测]{hyp}" if hyp else "[推测]信息不足"
    if not fc.get("node_clues"):
        fc["node_clues"] = fc.get("node_clues") or "Planner → Retriever → Guardrail（mock 推断）"
    if not fc.get("impact"):
        fc["impact"] = f"本周 {fc.get('run_count', 0)} 次"
    if not fc.get("priority"):
        fc["priority"] = "high" if (fc.get("run_count") or 0) >= 10 else "medium"

    check = validate_biz_problem(fc.get("biz_problem"))
    fc["biz_problem_valid"] = check["ok"]
    if not check["ok"]:
        fc["biz_problem_issues"] = check["issues"]
    return fc


def _finding_biz_probe(f: dict[str, Any]) -> str:
    return f"{f.get('biz_problem', '')} {f.get('impact', '')}"


def _collect_hold_finding_texts(exclude_report_id: str | None = None) -> list[dict[str, Any]]:
    """历史存疑 finding（仅 status=hold 的建议所关联 finding）。"""
    holds: list[dict[str, Any]] = []
    for report in MOCK_REVIEW_REPORTS:
        if exclude_report_id and report.get("id") == exclude_report_id:
            continue
        _ensure_suggestion_defaults(report)
        for sug in report.get("suggestions") or []:
            if sug.get("status") != SUGGESTION_HOLD:
                continue
            finding_id = sug.get("finding_id")
            run_ids = set(sug.get("evidence_run_ids") or [])
            for f in report.get("findings") or []:
                if finding_id and f.get("id") == finding_id:
                    holds.append({**f, "report_week": report.get("week"), "suggestion_id": sug.get("id")})
                    break
                if run_ids & set(f.get("run_ids") or []):
                    holds.append({**f, "report_week": report.get("week"), "suggestion_id": sug.get("id")})
                    break
    return holds


def attach_recurring_alerts(report: dict[str, Any]) -> dict[str, Any]:
    """复盘 Agent §5：语义比对历史存疑 finding，相似则标注提醒（mock 用文本相似度）。"""
    rep = dict(report)
    hold_findings = _collect_hold_finding_texts(exclude_report_id=rep.get("id"))
    if not hold_findings:
        return rep
    findings_out: list[dict[str, Any]] = []
    for raw in rep.get("findings") or []:
        f = normalize_finding_modules(raw)
        fc = dict(f)
        best: dict[str, Any] | None = None
        best_score = 0.0
        probe = _finding_biz_probe(f)
        for hf in hold_findings:
            hprobe = _finding_biz_probe(hf)
            score = _text_similarity(probe, hprobe)
            if score > best_score:
                best_score = score
                best = hf
        if best and best_score >= 0.45:
            fc["recurring_alert"] = (
                f"此问题上周已存疑，本周又发生 {f.get('run_count', 0)} 次，建议重新评估"
            )
            fc["recurring_from"] = best.get("id")
            fc["recurring_similarity"] = round(best_score, 2)
        findings_out.append(fc)
    rep["findings"] = findings_out
    return rep


def _parse_agent_nodes_from_clues(node_clues: str | None) -> list[str]:
    if not node_clues:
        return []
    parts = re.split(r"[→;；,，\s]+", node_clues.lower())
    known = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if "retriever" in p or "检索" in p:
            known.append("retriever")
        elif "planner" in p or "规划" in p:
            known.append("planner")
        elif "guardrail" in p or "拦截" in p:
            known.append("guardrail")
        elif "clarifier" in p or "澄清" in p:
            known.append("clarifier")
        elif "document" in p or "知识" in p:
            known.append("knowledge_index")
        elif "supervisor" in p:
            known.append("supervisor")
    return list(dict.fromkeys(known)) or ["planner", "supervisor"]


def _infer_agent_nodes(finding: dict[str, Any]) -> list[str]:
    parsed = _parse_agent_nodes_from_clues(finding.get("node_clues"))
    if parsed:
        return parsed
    text = f"{finding.get('phenomenon', '')} {finding.get('root_cause_hypothesis', '')}".lower()
    if "rag" in text or "知识库" in text or "0 命中" in text:
        return ["retriever", "knowledge_index", "guardrail"]
    if "over_reject" in text or "拦截" in text or "薪资" in text:
        return ["guardrail", "planner", "payroll_policy"]
    if "clarify" in text or "澄清" in text:
        return ["clarifier", "planner"]
    if "超时" in text or "timeout" in text:
        return ["supervisor", "attribution_subgraph"]
    return ["planner", "supervisor", "retriever"]


def _enrich_finding_technical(finding: dict[str, Any]) -> dict[str, Any]:
    """技术超管视图：仅模块 B + 技术线索框。"""
    fc = normalize_finding_modules(finding)
    run_ids = list(fc.get("evidence_run_ids") or [])
    nodes = _infer_agent_nodes(fc)
    fc["technical"] = {
        "agent_nodes": nodes,
        "run_ids": run_ids,
        "node_clues": fc.get("node_clues"),
        "phenomenon": fc.get("phenomenon"),
        "root_cause_hypothesis": fc.get("root_cause_hypothesis"),
        "category": fc.get("category"),
        "trace_hint": fc.get("trace_hint")
        or f"可在 Trace / 评测中心按 run_id 检索（本 finding 关联 {len(run_ids)} 个 run）",
    }
    return fc


def normalize_suggestion_modules(suggestion: dict[str, Any]) -> dict[str, Any]:
    """A 方案 §5：content_biz（人话）+ draft_changes（技术草稿）。"""
    s = dict(suggestion)
    if not s.get("content_biz"):
        legacy = (s.get("content") or s.get("title") or "").strip()
        s["content_biz"] = legacy or "系统需改进以更好回答该类员工问题"
    if not s.get("draft_changes"):
        s["draft_changes"] = {
            "target": s.get("change_target"),
            "action": s.get("title"),
            "add_test_case": s.get("test_requirement"),
        }
    check = validate_content_biz(s.get("content_biz"))
    s["content_biz_valid"] = check["ok"]
    if not check["ok"]:
        s["content_biz_issues"] = check["issues"]
    return s


def _suggestion_for_biz_view(suggestion: dict[str, Any]) -> dict[str, Any]:
    """业务超管：仅 content_biz + 决策状态，不含 draft_changes。"""
    s = normalize_suggestion_modules(suggestion)
    return {
        "id": s.get("id"),
        "content_biz": s.get("content_biz"),
        "risk": s.get("risk"),
        "status": s.get("status", SUGGESTION_PENDING),
        "ticket_id": s.get("ticket_id"),
        "reject_reason": s.get("reject_reason"),
        "hold_at": s.get("hold_at"),
        "content_biz_valid": s.get("content_biz_valid", True),
        "content_biz_issues": s.get("content_biz_issues"),
    }


def _suggestion_for_tech_view(suggestion: dict[str, Any]) -> dict[str, Any]:
    """技术超管：仅 draft_changes + 状态，不含 content_biz。"""
    s = normalize_suggestion_modules(suggestion)
    return {
        "id": s.get("id"),
        "draft_changes": s.get("draft_changes"),
        "draft_summary": format_draft_changes(s.get("draft_changes")),
        "risk": s.get("risk"),
        "status": s.get("status", SUGGESTION_PENDING),
        "ticket_id": s.get("ticket_id"),
        "reject_reason": s.get("reject_reason"),
        "hold_at": s.get("hold_at"),
    }


def _finding_for_biz_view(finding: dict[str, Any]) -> dict[str, Any]:
    """业务超管 API：仅暴露模块 A（不含技术字段）。"""
    f = normalize_finding_modules(finding)
    return {
        "id": f.get("id"),
        "finding_key": f.get("finding_key") or f.get("id"),
        "biz_problem": f.get("biz_problem"),
        "impact": f.get("impact"),
        "priority": f.get("priority"),
        "recurring_alert": f.get("recurring_alert"),
        "recurring_from": f.get("recurring_from"),
        "recurring_similarity": f.get("recurring_similarity"),
        "biz_problem_valid": f.get("biz_problem_valid", True),
        "biz_problem_issues": f.get("biz_problem_issues"),
    }


def enrich_review_report(report: dict[str, Any], *, role: str | None = None) -> dict[str, Any]:
    """按角色 enrich：业务超管含存疑提醒；技术超管只读+技术详情、无提醒。"""
    _ensure_suggestion_defaults(report)
    role_n = normalize_role(role) if role else BIZ_SUPER_ADMIN
    rep = dict(report)

    if role_n == TECH_SUPER_ADMIN:
        rep["view_mode"] = "tech_readonly"
        tech_findings: list[dict[str, Any]] = []
        for f in rep.get("findings") or []:
            fc = _enrich_finding_technical(f)
            for k in (
                "biz_problem",
                "impact",
                "priority",
                "biz_problem_valid",
                "biz_problem_issues",
                "recurring_alert",
                "recurring_from",
                "recurring_similarity",
                "text",
                "hypothesis",
            ):
                fc.pop(k, None)
            tech_findings.append(fc)
        rep["findings"] = tech_findings
        rep["suggestions"] = [_suggestion_for_tech_view(s) for s in rep.get("suggestions") or []]
        return rep

    rep = attach_recurring_alerts(rep)
    rep["findings"] = [_finding_for_biz_view(f) for f in rep.get("findings") or []]
    rep["suggestions"] = [_suggestion_for_biz_view(s) for s in rep.get("suggestions") or []]
    rep["view_mode"] = "biz_decision"
    rep["open_hold_findings"] = _build_open_hold_findings_payload()
    return rep


def _build_open_hold_findings_payload() -> list[dict[str, Any]]:
    """供复盘 Agent prompt 的 {{open_hold_findings}}（当前为 mock 聚合）。"""
    items: list[dict[str, Any]] = []
    for hf in _collect_hold_finding_texts():
        hf_n = normalize_finding_modules(hf)
        items.append(
            {
                "finding_key": hf_n.get("finding_key") or hf_n.get("id"),
                "biz_problem": hf_n.get("biz_problem"),
                "impact": hf_n.get("impact"),
                "report_week": hf.get("report_week"),
            }
        )
    return items


def list_hold_pending_suggestions() -> list[dict[str, Any]]:
    """跨周存疑待办（仅业务超管侧栏）。"""
    seed_demo_suggestion_states()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    items: list[dict[str, Any]] = []
    for report in MOCK_REVIEW_REPORTS:
        _ensure_suggestion_defaults(report)
        for sug in report.get("suggestions") or []:
            if sug.get("status") != SUGGESTION_HOLD:
                continue
            hold_at_s = sug.get("hold_at") or report.get("generated_at") or ""
            hold_days = 0
            try:
                hold_dt = datetime.fromisoformat(hold_at_s.replace("Z", ""))
                hold_days = max(0, (now - hold_dt).days)
            except (ValueError, TypeError):
                pass
            norm = normalize_suggestion_modules(sug)
            items.append(
                {
                    "suggestion_id": sug.get("id"),
                    "report_id": report.get("id"),
                    "report_week": report.get("week"),
                    "report_label": report.get("label"),
                    "report_period": report.get("period"),
                    "content_biz": norm.get("content_biz"),
                    "draft_changes": norm.get("draft_changes"),
                    "evidence_run_ids": sug.get("evidence_run_ids") or [],
                    "hold_at": hold_at_s,
                    "hold_days": hold_days,
                    "hold_weeks": max(1, hold_days // 7) if hold_days else 1,
                }
            )
    items.sort(key=lambda x: x.get("hold_at") or "", reverse=False)
    return items


def reject_review_suggestion(
    suggestion_id: str,
    *,
    reason: str,
    report_id: str | None = None,
) -> dict[str, Any]:
    found = _find_suggestion(suggestion_id, report_id)
    if not found:
        raise LookupError("suggestion not found")
    report, sug, _ = found
    if sug.get("status") == SUGGESTION_ACCEPTED:
        raise ValueError("已采纳的建议不能驳回")
    sug["status"] = SUGGESTION_REJECTED
    sug["reject_reason"] = reason.strip()
    sug["processed_at"] = _now_iso()
    return _serialize_suggestion(report, sug)


def hold_review_suggestion(suggestion_id: str, *, report_id: str | None = None) -> dict[str, Any]:
    found = _find_suggestion(suggestion_id, report_id)
    if not found:
        raise LookupError("suggestion not found")
    report, sug, _ = found
    if sug.get("status") == SUGGESTION_ACCEPTED:
        raise ValueError("已采纳的建议不能存疑")
    sug["status"] = SUGGESTION_HOLD
    sug["hold_at"] = _now_iso()
    sug["processed_at"] = sug["hold_at"]
    # 关联 finding（供复盘提醒）
    run_ids = set(sug.get("evidence_run_ids") or [])
    for f in report.get("findings") or []:
        if run_ids & set(f.get("run_ids") or []):
            sug["finding_id"] = f.get("id")
            break
    return _serialize_suggestion(report, sug)


def mark_suggestion_accepted(
    report_id: str,
    suggestion_id: str,
    *,
    ticket_id: int,
) -> None:
    found = _find_suggestion(suggestion_id, report_id)
    if not found:
        return
    _, sug, _ = found
    sug["status"] = SUGGESTION_ACCEPTED
    sug["ticket_id"] = ticket_id
    sug["processed_at"] = _now_iso()


def _serialize_suggestion(report: dict[str, Any], sug: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_suggestion_modules(sug)
    return {
        "id": sug.get("id"),
        "content_biz": norm.get("content_biz"),
        "status": sug.get("status", SUGGESTION_PENDING),
        "ticket_id": sug.get("ticket_id"),
        "reject_reason": sug.get("reject_reason"),
        "hold_at": sug.get("hold_at"),
        "report_id": report.get("id"),
        "report_label": report.get("label"),
        "report_week": report.get("week"),
        "report_period": report.get("period"),
    }


def seed_demo_suggestion_states() -> None:
    """演示：一条历史存疑 + 一条已采纳样式（内存，仅首次）。"""
    for report in MOCK_REVIEW_REPORTS:
        _ensure_suggestion_defaults(report)
    # w21 第二条标为存疑（右侧待办演示）
    w21 = next((r for r in MOCK_REVIEW_REPORTS if r.get("week") == "2026-W21"), None)
    if w21:
        for sug in w21.get("suggestions") or []:
            if sug.get("id") == "s2-w21" and sug.get("status") == SUGGESTION_PENDING:
                sug["status"] = SUGGESTION_HOLD
                sug["hold_at"] = "2026-05-14T09:00:00"
                sug["finding_id"] = "f2-w21"
                break
