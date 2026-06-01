"""Eval 数据访问层 — list/detail 序列化。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import EvalCaseResult, EvalRun


def _serialize_run(row: EvalRun, *, with_summary: bool = True) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": row.id,
        "version": row.version,
        "trigger": row.trigger,
        "triggered_by": row.triggered_by,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": row.duration_ms,
        "total_cases": row.total_cases,
        "layer1": {
            "total": row.layer1_total,
            "passed": row.layer1_pass,
            "accuracy": (row.layer1_pass / row.layer1_total) if row.layer1_total else None,
        },
        "layer2": {
            "total": row.layer2_total,
            "passed": row.layer2_pass,
            "hit_rate": (row.layer2_pass / row.layer2_total) if row.layer2_total else None,
        },
        "layer3": {
            "total": row.layer3_total,
            "scored": row.layer3_scored,
            "avg": row.layer3_avg,
            "correctness_avg": row.layer3_correctness_avg,
            "completeness_avg": row.layer3_completeness_avg,
            "citation_avg": row.layer3_citation_avg,
            "compliance_avg": row.layer3_compliance_avg,
        },
        "total_score": row.total_score,
    }
    if with_summary:
        summary["intent_breakdown"] = row.intent_breakdown or {}
        summary["weakness_summary"] = row.weakness_summary or []
        summary["notes"] = row.notes
    return summary


async def list_eval_runs(db: AsyncSession, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        await db.execute(select(EvalRun).order_by(desc(EvalRun.started_at)).limit(limit))
    ).scalars().all()
    return [_serialize_run(r, with_summary=False) for r in rows]


async def get_eval_run_detail(
    db: AsyncSession, run_id: int, *, include_cases: bool = True
) -> dict[str, Any] | None:
    row = await db.get(EvalRun, run_id)
    if not row:
        return None
    data = _serialize_run(row)
    # 计算与上次对比（仅 done 状态参与）
    prev_row = (
        await db.execute(
            select(EvalRun)
            .where(EvalRun.id != run_id, EvalRun.status == "done")
            .order_by(desc(EvalRun.started_at))
            .limit(1)
        )
    ).scalars().first()
    if prev_row:
        data["compare_prev"] = {
            "prev_id": prev_row.id,
            "prev_version": prev_row.version,
            "prev_total_score": prev_row.total_score,
            "prev_layer1_acc": (
                (prev_row.layer1_pass / prev_row.layer1_total) if prev_row.layer1_total else None
            ),
            "delta_total_score": _safe_delta(row.total_score, prev_row.total_score),
            "delta_layer1_acc": _safe_delta(
                (row.layer1_pass / row.layer1_total) if row.layer1_total else None,
                (prev_row.layer1_pass / prev_row.layer1_total) if prev_row.layer1_total else None,
            ),
        }
    if include_cases:
        cases = (
            await db.execute(
                select(EvalCaseResult)
                .where(EvalCaseResult.run_id == run_id)
                .order_by(EvalCaseResult.case_id, EvalCaseResult.layer)
            )
        ).scalars().all()
        data["case_results"] = [_serialize_case(c) for c in cases]
    return data


def _safe_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 4)


def _serialize_case(row: EvalCaseResult) -> dict[str, Any]:
    return {
        "case_id": row.case_id,
        "layer": row.layer,
        "passed": row.passed,
        "score": row.score,
        "score_detail": row.score_detail,
        "expected": row.expected,
        "actual": row.actual,
        "judge_reasoning": row.judge_reasoning,
        "violations": row.violations,
        "error": row.error,
    }


async def count_eval_runs(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(EvalRun)) or 0
