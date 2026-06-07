"""Eval 数据访问层 — list/detail 序列化。"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.eval.coverage import build_eval_coverage
from src.eval.loader import load_eval_set
from src.models import EvalCaseResult, EvalJudgeFeedback, EvalRun

RUN_TYPES = frozenset({"full", "l1_smoke", "gate"})
DIFF_CATEGORIES = frozenset({"new_fail", "fixed", "newly_added", "flaky", "unchanged", "no_baseline"})
GATE_ASSERT_THRESHOLD_DEFAULT = 0.85  # fallback when no full run baseline
LAYER1_GATE_THRESHOLD = 0.90  # legacy full-run display only
LAYER_TO_STAGE = {1: "planner", 2: "retrieve", 15: "resolver", 3: "answer"}
STAGE_PIPELINE_ORDER = {
    "planner": 0,
    "resolver": 1,
    "retrieve": 2,
    "analyst": 3,
    "critic": 4,
    "answer": 5,
}
DETERMINISTIC_ASSERTION_LAYERS = frozenset({1, 2})
JUDGE_CALIBRATION_MIN_SAMPLES = 20
LAYER_NOT_RUN_LABEL = "该层未运行"


def _run_type_from_row(row: EvalRun) -> str:
    rt = (row.run_type or "").strip()
    if rt in RUN_TYPES:
        return rt
    if row.notes == "layer1_only":
        return "l1_smoke"
    return "full"


def _eval_profile_from_run(row: EvalRun) -> str:
    rt = _run_type_from_row(row)
    if rt == "l1_smoke":
        return "layer1_only"
    if rt == "gate":
        return "gate"
    if row.notes in {"layer1_only", "full"}:
        return row.notes
    if row.layer2_total == 0 and row.layer3_total == 0 and row.layer1_total > 0:
        return "layer1_only"
    return "full"


async def resolve_gate_assert_threshold(db: AsyncSession) -> float:
    settings = get_settings()
    if settings.gate_assert_threshold is not None:
        return float(settings.gate_assert_threshold)
    if settings.gate_l1_threshold is not None:
        return float(settings.gate_l1_threshold)
    row = (
        await db.execute(
            select(EvalRun)
            .where(EvalRun.status == "done", EvalRun.run_type == "full")
            .order_by(desc(EvalRun.id))
            .limit(1)
        )
    ).scalars().first()
    if not row:
        return GATE_ASSERT_THRESHOLD_DEFAULT
    det_rows = (
        await db.execute(
            select(EvalCaseResult).where(
                EvalCaseResult.run_id == row.id,
                EvalCaseResult.layer.in_((1, 2)),
            )
        )
    ).scalars().all()
    if not det_rows:
        return GATE_ASSERT_THRESHOLD_DEFAULT
    rate_pct = (sum(1 for r in det_rows if r.passed) / len(det_rows)) * 100
    threshold_pct = math.floor(rate_pct / 5) * 5
    return max(threshold_pct, 5) / 100.0


async def resolve_gate_l1_threshold(db: AsyncSession) -> float:
    """Backward-compatible alias."""
    return await resolve_gate_assert_threshold(db)


def _assert_pass_rate(rows: list[EvalCaseResult]) -> float:
    det_rows = [r for r in rows if r.layer in DETERMINISTIC_ASSERTION_LAYERS]
    if not det_rows:
        return 0.0
    return sum(1 for r in det_rows if r.passed) / len(det_rows)


def _gate_summary_from_run(row: EvalRun) -> dict[str, Any]:
    profile = _eval_profile_from_run(row)
    if not row.layer1_total:
        return {"gate_status": "no_data", "gate_passed": None, "planner_accuracy": None}
    acc = row.layer1_pass / row.layer1_total
    planner_accuracy = round(acc, 4)
    if profile == "layer1_only":
        return {
            "gate_status": "no_data",
            "gate_passed": None,
            "planner_accuracy": planner_accuracy,
        }
    return {
        "gate_status": "ok",
        "gate_passed": acc >= LAYER1_GATE_THRESHOLD,
        "planner_accuracy": planner_accuracy,
    }


def _serialize_run(
    row: EvalRun,
    *,
    with_summary: bool = True,
    case_results: list[EvalCaseResult] | None = None,
) -> dict[str, Any]:
    run_type = _run_type_from_row(row)
    summary: dict[str, Any] = {
        "id": row.id,
        "version": row.version,
        "trigger": row.trigger,
        "triggered_by": row.triggered_by,
        "status": row.status,
        "run_type": run_type,
        "source_ticket_id": row.source_ticket_id,
        "baseline_run_id": row.baseline_run_id,
        "eval_set_version": row.eval_set_version,
        "gate_verdict": row.gate_verdict,
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
        "eval_profile": _eval_profile_from_run(row),
        **_gate_summary_from_run(row),
    }
    if with_summary:
        summary["intent_breakdown"] = row.intent_breakdown or {}
        summary["weakness_summary"] = row.weakness_summary or []
        summary["notes"] = row.notes
        if run_type == "gate":
            summary["gate_diff"] = _gate_diff_counts_from_run(row, case_results=case_results)
    return summary


def _gate_diff_counts_from_run(
    row: EvalRun, *, case_results: list[EvalCaseResult] | None = None
) -> dict[str, int]:
    counts = {"new_fail": 0, "fixed": 0, "newly_added": 0, "flaky": 0, "unchanged": 0}
    rows = case_results if case_results is not None else []
    for cr in rows:
        if cr.layer != 1 or not cr.diff_category:
            continue
        cat = cr.diff_category
        if cat in counts:
            counts[cat] += 1
    return counts


async def list_eval_runs(
    db: AsyncSession, *, limit: int = 20, run_type: str | None = None
) -> list[dict[str, Any]]:
    demo_rank = case((EvalRun.trigger == "demo", 1), else_=0)
    query = select(EvalRun)
    if run_type:
        rt = run_type.strip()
        if rt == "l1_smoke":
            query = query.where(
                (EvalRun.run_type == "l1_smoke") | ((EvalRun.run_type.is_(None)) & (EvalRun.notes == "layer1_only"))
            )
        elif rt in RUN_TYPES:
            query = query.where(EvalRun.run_type == rt)
    rows = (
        await db.execute(query.order_by(demo_rank, desc(EvalRun.started_at)).limit(limit))
    ).scalars().all()
    return [_serialize_run(r, with_summary=False) for r in rows]


async def get_eval_run_detail(
    db: AsyncSession, run_id: int, *, include_cases: bool = True
) -> dict[str, Any] | None:
    row = await db.get(EvalRun, run_id)
    if not row:
        return None
    gate_case_rows: list[EvalCaseResult] | None = None
    if _run_type_from_row(row) == "gate":
        gate_case_rows = (
            await db.execute(
                select(EvalCaseResult).where(
                    EvalCaseResult.run_id == run_id,
                    EvalCaseResult.layer == 1,
                )
            )
        ).scalars().all()
    data = _serialize_run(row, case_results=gate_case_rows)
    # 计算与上次对比（仅 done 状态参与）
    prev_row = (
        await db.execute(
            select(EvalRun)
            .where(EvalRun.id < run_id, EvalRun.status == "done")
            .order_by(desc(EvalRun.id))
            .limit(1)
        )
    ).scalars().first()
    if prev_row:
        data["compare_prev"] = {
            "prev_id": prev_row.id,
            "prev_version": prev_row.version,
            "prev_total_score": prev_row.total_score,
            "prev_layer3_avg": prev_row.layer3_avg,
            "prev_layer1_acc": (
                (prev_row.layer1_pass / prev_row.layer1_total) if prev_row.layer1_total else None
            ),
            "delta_total_score": _safe_delta(row.total_score, prev_row.total_score),
            "delta_layer3_avg": _safe_delta(row.layer3_avg, prev_row.layer3_avg),
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
        if _run_type_from_row(row) == "gate":
            gate_cats = await resolve_gate_diff_categories(db, row, cases)
            feedback_map = await _feedback_map_for_results(db, [c.id for c in cases if c.id])
            data["case_results"] = _build_gate_case_items(
                cases, gate_cats=gate_cats, feedback_map=feedback_map
            )
        else:
            meta = _case_meta_map()
            data["case_results"] = [
                _serialize_case(c, meta=meta.get(c.case_id, {})) for c in cases
            ]
    return data


def _safe_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 4)


def _serialize_case(row: EvalCaseResult, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = meta or {}
    scored = row.layer == 3 and row.score is not None and not row.error
    flaky = bool((row.score_detail or {}).get("flaky")) or row.diff_category == "flaky"
    return {
        "id": row.id,
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
        "scored": scored,
        "flaky": flaky,
        "diff_category": row.diff_category,
        "attempts": row.attempts,
        "pass_count": row.pass_count,
        "query": meta.get("query"),
        "intent": meta.get("intent"),
        "declared_layers": meta.get("declared_layers") or [row.layer],
        "feedback": meta.get("feedback"),
    }


def _case_meta_map() -> dict[str, dict[str, Any]]:
    return {
        c["id"]: {
            "query": c.get("query"),
            "intent": (c.get("expected") or {}).get("intent"),
            "declared_layers": list(c.get("layer") or [1]),
        }
        for c in load_eval_set()
    }


def _all_eval_case_ids() -> set[str]:
    return {c["id"] for c in load_eval_set()}


def _serialize_pending_gate_case(
    case_id: str,
    *,
    meta: dict[str, Any],
    diff_category: str | None,
) -> dict[str, Any]:
    return {
        "id": None,
        "case_id": case_id,
        "layer": 1,
        "passed": None,
        "score": None,
        "score_detail": None,
        "expected": None,
        "actual": None,
        "judge_reasoning": None,
        "violations": None,
        "error": None,
        "scored": False,
        "flaky": False,
        "pending": True,
        "diff_category": diff_category,
        "attempts": None,
        "pass_count": None,
        "query": meta.get("query"),
        "intent": meta.get("intent"),
        "declared_layers": meta.get("declared_layers") or [1],
        "feedback": None,
    }


def _build_gate_case_items(
    rows: list[EvalCaseResult],
    *,
    gate_cats: dict[str, str] | None,
    feedback_map: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return all eval-set cases for gate runs; fill placeholders for not-yet-run cases."""
    meta = _case_meta_map()
    feedback_map = feedback_map or {}
    rows_by_case: dict[str, list[EvalCaseResult]] = {}
    for row in rows:
        rows_by_case.setdefault(row.case_id, []).append(row)

    items: list[dict[str, Any]] = []
    for case in load_eval_set():
        cid = case["id"]
        case_meta = meta.get(cid, {})
        case_rows = rows_by_case.get(cid, [])
        if case_rows:
            for row in case_rows:
                item = _serialize_case(
                    row,
                    meta={
                        **case_meta,
                        "feedback": feedback_map.get(row.id),
                    },
                )
                if row.layer == 1 and gate_cats:
                    item["diff_category"] = gate_cats.get(cid, item.get("diff_category"))
                items.append(item)
        else:
            cat = (gate_cats or {}).get(cid)
            items.append(
                _serialize_pending_gate_case(cid, meta=case_meta, diff_category=cat)
            )
    return items


async def list_run_cases(db: AsyncSession, run_id: int) -> dict[str, Any] | None:
    """Return case rows + metrics computed from the same EvalCaseResult batch."""
    return await get_run_cases_payload(db, run_id)


async def get_run_cases_payload(db: AsyncSession, run_id: int) -> dict[str, Any] | None:
    run = await db.get(EvalRun, run_id)
    if not run:
        return None
    rows = (
        await db.execute(
            select(EvalCaseResult)
            .where(EvalCaseResult.run_id == run_id)
            .order_by(EvalCaseResult.passed.asc(), EvalCaseResult.layer.asc(), EvalCaseResult.case_id)
        )
    ).scalars().all()
    feedback_map = await _feedback_map_for_results(db, [r.id for r in rows])
    if _run_type_from_row(run) == "gate":
        gate_cats = await resolve_gate_diff_categories(db, run, rows)
        items = _build_gate_case_items(rows, gate_cats=gate_cats, feedback_map=feedback_map)
    else:
        meta = _case_meta_map()
        items = [
            _serialize_case(
                row,
                meta={
                    **meta.get(row.case_id, {}),
                    "feedback": feedback_map.get(row.id),
                },
            )
            for row in rows
        ]
    metrics = await build_run_metrics_from_rows(db, run_id, rows)
    return {"run_id": run_id, "items": items, "metrics": metrics}


def _infer_eval_profile(rows: list[EvalCaseResult]) -> str:
    has_l2 = any(r.layer == 2 for r in rows)
    has_l3 = any(r.layer == 3 for r in rows)
    if not has_l2 and not has_l3 and any(r.layer == 1 for r in rows):
        return "layer1_only"
    return "full"


def _cluster_label(stage: str, intent: str) -> str:
    suffix = ""
    if stage == "retrieve":
        suffix = " · 取证路"
    return f"{stage} · {intent}{suffix}"


def compute_failure_clusters(
    rows: list[EvalCaseResult],
    meta: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Cluster failed case rows by pipeline stage × intent (same source as case table)."""
    meta = meta or _case_meta_map()
    clusters: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        if row.passed:
            continue
        stage = LAYER_TO_STAGE.get(row.layer, f"layer{row.layer}")
        intent = meta.get(row.case_id, {}).get("intent") or "unknown"
        clusters.setdefault((stage, intent), []).append(row.case_id)

    failure_clusters = [
        {
            "stage": stage,
            "intent": intent,
            "count": len(case_ids),
            "case_ids": sorted(set(case_ids)),
            "label": _cluster_label(stage, intent),
        }
        for (stage, intent), case_ids in clusters.items()
    ]
    failure_clusters.sort(
        key=lambda x: (
            -x["count"],
            STAGE_PIPELINE_ORDER.get(x["stage"], 99),
            x["intent"],
        )
    )
    return failure_clusters


def compute_metrics_from_case_rows(rows: list[EvalCaseResult], *, run: EvalRun | None = None) -> dict[str, Any]:
    """Single source of truth for assertion / grader / gate / weakest cards."""
    profile = _eval_profile_from_run(run) if run else _infer_eval_profile(rows)
    det_rows = [r for r in rows if r.layer in DETERMINISTIC_ASSERTION_LAYERS]
    assertion_passed = sum(1 for r in det_rows if r.passed)
    assertion_total = len(det_rows)

    l3_scored = [r for r in rows if r.layer == 3 and r.score is not None]
    grader_avg = (
        round(sum(float(r.score) for r in l3_scored) / len(l3_scored), 2) if l3_scored else None
    )

    l1_rows = [r for r in rows if r.layer == 1]
    if not l1_rows:
        gate_status = "no_data"
        gate_passed: bool | None = None
        planner_accuracy = None
    elif profile == "layer1_only":
        gate_status = "no_data"
        gate_passed = None
        l1_pass = sum(1 for r in l1_rows if r.passed)
        planner_accuracy = round(l1_pass / len(l1_rows), 4)
    elif profile == "gate":
        gate_status = "ok"
        l1_pass = sum(1 for r in l1_rows if r.passed)
        planner_accuracy = round(l1_pass / len(l1_rows), 4) if l1_rows else None
        gate_passed = run.gate_verdict == "pass" if run else None
    else:
        gate_status = "ok"
        l1_pass = sum(1 for r in l1_rows if r.passed)
        planner_accuracy = l1_pass / len(l1_rows)
        gate_passed = planner_accuracy >= LAYER1_GATE_THRESHOLD
        planner_accuracy = round(planner_accuracy, 4)

    clusters = compute_failure_clusters(rows)
    weakest_link = clusters[0]["label"] if clusters else "无失败"

    return {
        "eval_profile": profile,
        "assertion": {"passed": assertion_passed, "total": assertion_total},
        "grader_avg": grader_avg if profile == "full" else None,
        "grader_scored_count": len(l3_scored) if profile == "full" else 0,
        "gate_status": gate_status,
        "gate_passed": gate_passed,
        "planner_accuracy": planner_accuracy,
        "failure_clusters": clusters,
        "weakest_link": weakest_link,
    }


async def build_run_metrics_from_rows(
    db: AsyncSession, run_id: int, rows: list[EvalCaseResult]
) -> dict[str, Any]:
    run = await db.get(EvalRun, run_id)
    metrics = compute_metrics_from_case_rows(rows, run=run)
    prev_row = await _resolve_baseline_run(db, run_id)
    if prev_row and metrics["grader_avg"] is not None:
        prev_rows = (
            await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == prev_row.id))
        ).scalars().all()
        prev_avg = compute_metrics_from_case_rows(prev_rows, run=prev_row).get("grader_avg")
        metrics["delta_grader_avg"] = _safe_delta(metrics["grader_avg"], prev_avg)
    else:
        metrics["delta_grader_avg"] = None
    metrics["judge_calibration"] = await compute_judge_calibration(db, run_id=run_id)
    metrics["flaky_count"] = sum(
        1 for r in rows if r.layer == 1 and (r.score_detail or {}).get("flaky")
    )
    metrics["failure_clusters"] = metrics.get("failure_clusters") or compute_failure_clusters(rows)
    metrics["gate_l1_threshold"] = await resolve_gate_assert_threshold(db)
    metrics["gate_assert_threshold"] = metrics["gate_l1_threshold"]
    if run and _run_type_from_row(run) == "gate":
        has_baseline = bool(run.baseline_run_id)
        ticket_new_ids: list[str] | None = None
        if run.source_ticket_id:
            from src.models import ImprovementTicket

            ticket = await db.get(ImprovementTicket, run.source_ticket_id)
            ticket_new_ids = list(ticket.new_case_ids or []) if ticket else []
        cats = await resolve_gate_diff_categories(db, run, rows)
        cur_ids = {r.case_id for r in rows if r.layer == 1}
        total_cases = run.total_cases or len(_all_eval_case_ids())
        metrics["gate_diff"] = summarize_gate_diff(
            cats,
            new_case_ids=ticket_new_ids,
            current_case_ids=cur_ids,
            has_baseline=has_baseline,
        )
        metrics["has_baseline"] = has_baseline
        metrics["baseline_run_id"] = run.baseline_run_id
        metrics["eval_set_version"] = run.eval_set_version
        metrics["progress"] = {"completed": len(cur_ids), "total": total_cases}
        if run.status == "done":
            metrics["gate_verdict"] = run.gate_verdict
            _, verdict_detail = await compute_gate_verdict(
                db, run, new_case_ids=ticket_new_ids, categories=cats
            )
            metrics["gate_verdict_detail"] = verdict_detail
        else:
            metrics["gate_verdict"] = None
            metrics["gate_verdict_detail"] = None
    metrics["weakest_link"] = metrics.get("weakest_link") or (
        metrics["failure_clusters"][0]["label"] if metrics["failure_clusters"] else "无失败"
    )
    return metrics


async def attach_run_metrics_from_cases(db: AsyncSession, run_id: int, data: dict[str, Any]) -> None:
    rows = (
        await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == run_id))
    ).scalars().all()
    metrics = await build_run_metrics_from_rows(db, run_id, rows)
    data["assertion"] = metrics["assertion"]
    data["grader_avg"] = metrics["grader_avg"]
    data["grader_scored_count"] = metrics["grader_scored_count"]
    data["gate_status"] = metrics["gate_status"]
    data["gate_passed"] = metrics["gate_passed"]
    data["planner_accuracy"] = metrics["planner_accuracy"]
    data["delta_grader_avg"] = metrics.get("delta_grader_avg")
    data["judge_calibration"] = metrics["judge_calibration"]
    data["weakest_link"] = metrics.get("weakest_link")
    data["failure_clusters"] = metrics.get("failure_clusters")
    data["gate_diff"] = metrics.get("gate_diff")
    data["gate_verdict_detail"] = metrics.get("gate_verdict_detail")
    data["gate_assert_threshold"] = metrics.get("gate_assert_threshold")
    data["has_baseline"] = metrics.get("has_baseline")
    data["progress"] = metrics.get("progress")


async def _feedback_map_for_results(
    db: AsyncSession, result_ids: list[int]
) -> dict[int, dict[str, Any]]:
    if not result_ids:
        return {}
    rows = (
        await db.execute(
            select(EvalJudgeFeedback)
            .where(EvalJudgeFeedback.case_result_id.in_(result_ids))
            .order_by(desc(EvalJudgeFeedback.created_at))
        )
    ).scalars().all()
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.case_result_id in out:
            continue
        out[row.case_result_id] = {
            "id": row.id,
            "verdict": row.verdict,
            "human_overall": row.human_overall,
            "note": row.note,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    return out


async def _resolve_baseline_run(
    db: AsyncSession, run_id: int, against: int | None = None
) -> EvalRun | None:
    if against is not None:
        return await db.get(EvalRun, against)
    current = await db.get(EvalRun, run_id)
    if not current:
        return None
    return (
        await db.execute(
            select(EvalRun)
            .where(EvalRun.id < run_id, EvalRun.status == "done")
            .order_by(desc(EvalRun.id))
            .limit(1)
        )
    ).scalars().first()


def _case_pass_map(rows: list[EvalCaseResult]) -> dict[str, bool]:
    grouped: dict[str, list[bool]] = {}
    for row in rows:
        grouped.setdefault(row.case_id, []).append(row.passed)
    return {case_id: all(passed) for case_id, passed in grouped.items()}


def _case_diff_category_map(rows: list[EvalCaseResult]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        if row.layer == 1 and row.diff_category:
            out[row.case_id] = row.diff_category
    return out


def compute_gate_diff(
    *,
    current_rows: list[EvalCaseResult],
    baseline_rows: list[EvalCaseResult],
    new_case_ids: list[str] | None = None,
    has_baseline: bool | None = None,
    all_case_ids: set[str] | None = None,
) -> dict[str, str]:
    """Return case_id -> diff_category for gate runs."""
    cur_map = _case_pass_map(current_rows)
    base_map = _case_pass_map(baseline_rows)
    ticket_new = set(new_case_ids or [])
    eval_ids = all_case_ids if all_case_ids is not None else _all_eval_case_ids()
    has_baseline = bool(baseline_rows) if has_baseline is None else has_baseline
    categories: dict[str, str] = {}

    if not has_baseline:
        for case_id in sorted(eval_ids | ticket_new):
            categories[case_id] = "newly_added" if case_id in ticket_new else "no_baseline"
        return categories

    all_ids = sorted(eval_ids | set(base_map) | ticket_new)
    for case_id in all_ids:
        if case_id in ticket_new:
            categories[case_id] = "newly_added"
            continue
        cur_ok = cur_map.get(case_id)
        base_ok = base_map.get(case_id)
        if case_id not in base_map:
            categories[case_id] = "new_fail" if cur_ok is False else "unchanged"
        elif case_id not in cur_map:
            categories[case_id] = "unchanged"
        elif base_ok and cur_ok is False:
            categories[case_id] = "new_fail"
        elif not base_ok and cur_ok:
            categories[case_id] = "fixed"
        else:
            categories[case_id] = "unchanged"
    return categories


async def resolve_gate_diff_categories(
    db: AsyncSession,
    run: EvalRun,
    rows: list[EvalCaseResult],
) -> dict[str, str]:
    """Recompute gate diff categories (preserves flaky overrides from persistence)."""
    baseline_rows: list[EvalCaseResult] = []
    if run.baseline_run_id:
        baseline_rows = (
            await db.execute(
                select(EvalCaseResult).where(EvalCaseResult.run_id == run.baseline_run_id)
            )
        ).scalars().all()
    ticket_new_ids: list[str] | None = None
    if run.source_ticket_id:
        from src.models import ImprovementTicket

        ticket = await db.get(ImprovementTicket, run.source_ticket_id)
        ticket_new_ids = list(ticket.new_case_ids or []) if ticket else []
    cats = compute_gate_diff(
        current_rows=rows,
        baseline_rows=baseline_rows,
        new_case_ids=ticket_new_ids,
        has_baseline=bool(run.baseline_run_id),
    )
    for row in rows:
        if row.layer == 1 and row.diff_category == "flaky":
            cats[row.case_id] = "flaky"
    return cats


async def apply_gate_diff_to_results(
    db: AsyncSession,
    run_id: int,
    *,
    baseline_run_id: int | None,
    new_case_ids: list[str] | None = None,
    flaky_overrides: dict[str, tuple[int, int]] | None = None,
) -> dict[str, str]:
    """Persist diff_category on layer-1 rows; return categories."""
    current_rows = (
        await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == run_id))
    ).scalars().all()
    baseline_rows: list[EvalCaseResult] = []
    if baseline_run_id:
        baseline_rows = (
            await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == baseline_run_id))
        ).scalars().all()
    categories = compute_gate_diff(
        current_rows=current_rows,
        baseline_rows=baseline_rows,
        new_case_ids=new_case_ids,
        has_baseline=bool(baseline_run_id),
    )
    flaky_overrides = flaky_overrides or {}
    for row in current_rows:
        if row.layer != 1:
            continue
        cat = categories.get(row.case_id, "unchanged")
        if row.case_id in flaky_overrides:
            attempts, pass_count = flaky_overrides[row.case_id]
            row.attempts = attempts
            row.pass_count = pass_count
            if pass_count >= 2:
                cat = "flaky"
                row.passed = True
                detail = dict(row.score_detail or {})
                detail["flaky"] = True
                row.score_detail = detail
        row.diff_category = cat
    await db.commit()
    return categories


def summarize_gate_diff(
    categories: dict[str, str],
    *,
    new_case_ids: list[str] | None = None,
    current_case_ids: set[str] | None = None,
    has_baseline: bool = True,
) -> dict[str, Any]:
    counts: dict[str, Any] = {
        "new_fail": 0,
        "fixed": 0,
        "newly_added": 0,
        "flaky": 0,
        "unchanged": 0,
        "no_baseline": 0,
        "has_baseline": has_baseline,
    }
    for cat in categories.values():
        if cat in counts:
            counts[cat] += 1
    ticket_new = list(new_case_ids or [])
    hits = current_case_ids or set(categories)
    counts["ticket_new_declared"] = len(ticket_new)
    counts["newly_added"] = sum(1 for cid in ticket_new if cid in hits)
    return counts


async def compute_gate_verdict(
    db: AsyncSession,
    run: EvalRun,
    *,
    new_case_ids: list[str] | None = None,
    categories: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ('pass'|'fail', detail dict with reasons[])."""
    rows = (
        await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == run.id))
    ).scalars().all()
    if categories is None:
        categories = await resolve_gate_diff_categories(db, run, rows)
    cur_map = _case_pass_map(rows)
    has_baseline = bool(run.baseline_run_id)
    counts = summarize_gate_diff(
        categories,
        new_case_ids=new_case_ids,
        current_case_ids=set(cur_map),
        has_baseline=has_baseline,
    )
    threshold = await resolve_gate_assert_threshold(db)
    assert_rate = _assert_pass_rate(rows)
    assert_ok = assert_rate >= threshold

    new_case_failures: list[str] = []
    for cid in new_case_ids or []:
        cat = categories.get(cid)
        if cat == "flaky":
            continue
        if not cur_map.get(cid, False):
            new_case_failures.append(cid)

    reasons: list[str] = []
    if has_baseline and counts["new_fail"] > 0:
        reasons.append(f"新挂 {counts['new_fail']} 条")
    if new_case_failures:
        reasons.append(f"工单新增用例未全过：{', '.join(new_case_failures)}")
    if not assert_ok:
        reasons.append(f"断言通过率 {assert_rate * 100:.1f}% < {threshold * 100:.0f}%")

    passed = (not has_baseline or counts["new_fail"] == 0) and assert_ok and not new_case_failures
    detail = {
        "gate_verdict": "pass" if passed else "fail",
        "gate_assert_threshold": round(threshold, 4),
        "gate_l1_threshold": round(threshold, 4),
        "assert_pass_rate": round(assert_rate, 4),
        "planner_accuracy": round((run.layer1_pass / run.layer1_total), 4) if run.layer1_total else None,
        "new_fail_count": counts["new_fail"],
        "fixed_count": counts["fixed"],
        "newly_added_count": counts["newly_added"],
        "flaky_count": counts["flaky"],
        "no_baseline_count": counts["no_baseline"],
        "has_baseline": has_baseline,
        "new_case_failures": new_case_failures,
        "reasons": reasons,
    }
    return ("pass" if passed else "fail", detail)


async def set_eval_baseline(db: AsyncSession, run_id: int) -> dict[str, Any]:
    """Manually set released baseline pointer to a completed full run."""
    from src.eval.baseline import set_released_baseline_run_id

    run = await db.get(EvalRun, run_id)
    if not run:
        raise LookupError("eval run not found")
    if _run_type_from_row(run) != "full":
        raise ValueError("仅已完成的全量 run 可设为基线")
    if run.status != "done":
        raise ValueError("仅已完成的全量 run 可设为基线")
    await set_released_baseline_run_id(db, run_id)
    return {"run_id": run_id, "baseline_run_id": run_id}


async def get_run_diff(
    db: AsyncSession, run_id: int, *, against: int | None = None
) -> dict[str, Any] | None:
    current = await db.get(EvalRun, run_id)
    if not current:
        return None
    if _run_type_from_row(current) == "gate":
        rows = (
            await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == run_id))
        ).scalars().all()
        meta = _case_meta_map()
        cats = await resolve_gate_diff_categories(db, current, rows)
        regressed = [cid for cid, cat in cats.items() if cat == "new_fail"]
        fixed = [cid for cid, cat in cats.items() if cat == "fixed"]
        newly_added = [cid for cid, cat in cats.items() if cat == "newly_added"]
        no_baseline = [cid for cid, cat in cats.items() if cat == "no_baseline"]
        flaky = [cid for cid, cat in cats.items() if cat == "flaky"]
        return {
            "run_id": run_id,
            "against_run_id": current.baseline_run_id,
            "has_baseline": bool(current.baseline_run_id),
            "regressed": regressed,
            "fixed": fixed,
            "newly_added": newly_added,
            "no_baseline": no_baseline,
            "flaky": flaky,
            "failure_clusters": compute_failure_clusters(rows, meta),
        }
    baseline = await _resolve_baseline_run(db, run_id, against)
    current_rows = (
        await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == run_id))
    ).scalars().all()
    meta = _case_meta_map()
    regressed: list[str] = []
    fixed: list[str] = []
    if baseline:
        baseline_rows = (
            await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == baseline.id))
        ).scalars().all()
        cur_map = _case_pass_map(current_rows)
        base_map = _case_pass_map(baseline_rows)
        all_ids = sorted(set(cur_map) | set(base_map))
        for case_id in all_ids:
            cur_ok = cur_map.get(case_id, True)
            base_ok = base_map.get(case_id, True)
            if base_ok and not cur_ok:
                regressed.append(case_id)
            elif not base_ok and cur_ok:
                fixed.append(case_id)

    failure_clusters = compute_failure_clusters(current_rows, meta)

    return {
        "run_id": run_id,
        "against_run_id": baseline.id if baseline else None,
        "regressed": regressed,
        "fixed": fixed,
        "failure_clusters": failure_clusters,
    }


def get_eval_coverage() -> dict[str, Any]:
    return build_eval_coverage()


async def compute_judge_calibration(
    db: AsyncSession, *, run_id: int | None = None
) -> dict[str, Any]:
    """Judge vs human agreement rate.

    Real runs: only feedback on that run's case results.
    Demo runs: all feedback across demo runs (seed pool on v1.4.0 + demo session feedback).
    """
    stmt = (
        select(EvalJudgeFeedback, EvalCaseResult)
        .join(EvalCaseResult, EvalCaseResult.id == EvalJudgeFeedback.case_result_id)
        .where(EvalJudgeFeedback.human_overall.is_not(None))
    )
    if run_id is not None:
        run_row = await db.get(EvalRun, run_id)
        if run_row and run_row.trigger == "demo":
            stmt = stmt.join(EvalRun, EvalRun.id == EvalCaseResult.run_id).where(
                EvalRun.trigger == "demo"
            )
        else:
            stmt = stmt.where(EvalCaseResult.run_id == run_id)
    stmt = stmt.order_by(desc(EvalJudgeFeedback.created_at), desc(EvalJudgeFeedback.id))
    rows = (await db.execute(stmt)).all()
    latest_by_case: dict[int, tuple[float, int]] = {}
    for fb, case_row in rows:
        if case_row.id in latest_by_case:
            continue
        if case_row.score is None:
            continue
        human = fb.human_overall
        if human is None and fb.verdict == "agree":
            human = max(1, min(5, int(round(float(case_row.score)))))
        if human is None:
            continue
        latest_by_case[case_row.id] = (float(case_row.score), int(human))
    samples = list(latest_by_case.values())
    sample_count = len(samples)
    if sample_count == 0:
        return {"sample_count": 0, "agreement_rate": None, "warn": False, "insufficient": True}
    if sample_count < JUDGE_CALIBRATION_MIN_SAMPLES:
        return {
            "sample_count": sample_count,
            "agreement_rate": None,
            "warn": False,
            "insufficient": True,
        }
    agreed = sum(1 for judge, human in samples if abs(judge - human) <= 1)
    rate = round(agreed / sample_count, 4)
    return {
        "sample_count": sample_count,
        "agreement_rate": rate,
        "warn": rate < 0.8,
        "insufficient": False,
    }


async def submit_judge_feedback(
    db: AsyncSession,
    *,
    case_result_id: int,
    verdict: str,
    human_overall: int | None,
    note: str | None,
    created_by: str,
) -> dict[str, Any]:
    if verdict not in {"agree", "disagree"}:
        raise ValueError("verdict must be agree or disagree")
    case_row = await db.get(EvalCaseResult, case_result_id)
    if not case_row:
        raise LookupError("case result not found")
    if case_row.layer != 3:
        raise ValueError("feedback only allowed for layer 3 judge results")
    if case_row.score is None:
        raise ValueError("feedback requires a scored judge result")

    run_row = await db.get(EvalRun, case_row.run_id)
    if run_row and run_row.trigger != "demo":
        existing = (
            await db.execute(
                select(EvalJudgeFeedback.id)
                .where(EvalJudgeFeedback.case_result_id == case_result_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError("feedback already submitted for this case")

    if verdict == "agree":
        human_overall = max(1, min(5, int(round(float(case_row.score)))))
    elif human_overall is None:
        raise ValueError("disagree requires human_overall (1-5)")
    elif not (1 <= human_overall <= 5):
        raise ValueError("human_overall must be 1-5")

    row = EvalJudgeFeedback(
        case_result_id=case_result_id,
        verdict=verdict,
        human_overall=human_overall,
        note=(note or "").strip() or None,
        created_by=created_by,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {
        "id": row.id,
        "case_result_id": row.case_result_id,
        "verdict": row.verdict,
        "human_overall": row.human_overall,
        "note": row.note,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def assertion_stats(run: EvalRun) -> dict[str, int | None]:
    total = (run.layer1_total or 0) + (run.layer2_total or 0)
    passed = (run.layer1_pass or 0) + (run.layer2_pass or 0)
    return {"passed": passed, "total": total}


def gate_passed_for_run(run: EvalRun) -> bool:
    if not run.layer1_total:
        return False
    return (run.layer1_pass / run.layer1_total) >= LAYER1_GATE_THRESHOLD


async def count_eval_runs(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(EvalRun)) or 0


async def delete_garbage_eval_runs(db: AsyncSession) -> int:
    """Remove test runs with placeholder version labels (e.g. 't')."""
    from src.eval.version import is_garbage_eval_version

    rows = (await db.execute(select(EvalRun))).scalars().all()
    doomed = [r for r in rows if is_garbage_eval_version(r.version)]
    for row in doomed:
        await db.delete(row)
    if doomed:
        await db.commit()
    return len(doomed)
