"""Eval 数据访问层 — list/detail 序列化。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.eval.coverage import build_eval_coverage
from src.eval.loader import load_eval_set
from src.models import EvalCaseResult, EvalJudgeFeedback, EvalRun

LAYER1_GATE_THRESHOLD = 0.90
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


def _eval_profile_from_run(row: EvalRun) -> str:
    if row.notes in {"layer1_only", "full"}:
        return row.notes
    if row.layer2_total == 0 and row.layer3_total == 0 and row.layer1_total > 0:
        return "layer1_only"
    return "full"


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
        "eval_profile": _eval_profile_from_run(row),
        **_gate_summary_from_run(row),
    }
    if with_summary:
        summary["intent_breakdown"] = row.intent_breakdown or {}
        summary["weakness_summary"] = row.weakness_summary or []
        summary["notes"] = row.notes
    return summary


async def list_eval_runs(db: AsyncSession, *, limit: int = 20) -> list[dict[str, Any]]:
    demo_rank = case((EvalRun.trigger == "demo", 1), else_=0)
    rows = (
        await db.execute(
            select(EvalRun)
            .order_by(demo_rank, desc(EvalRun.started_at))
            .limit(limit)
        )
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
        data["case_results"] = [_serialize_case(c, meta=_case_meta_map().get(c.case_id, {})) for c in cases]
    return data


def _safe_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 4)


def _serialize_case(row: EvalCaseResult, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = meta or {}
    scored = row.layer == 3 and row.score is not None and not row.error
    flaky = bool((row.score_detail or {}).get("flaky"))
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


def compute_metrics_from_case_rows(rows: list[EvalCaseResult]) -> dict[str, Any]:
    """Single source of truth for assertion / grader / gate / weakest cards."""
    profile = _infer_eval_profile(rows)
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
    metrics = compute_metrics_from_case_rows(rows)
    prev_row = await _resolve_baseline_run(db, run_id)
    if prev_row and metrics["grader_avg"] is not None:
        prev_rows = (
            await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == prev_row.id))
        ).scalars().all()
        prev_avg = compute_metrics_from_case_rows(prev_rows).get("grader_avg")
        metrics["delta_grader_avg"] = _safe_delta(metrics["grader_avg"], prev_avg)
    else:
        metrics["delta_grader_avg"] = None
    metrics["judge_calibration"] = await compute_judge_calibration(db, run_id=run_id)
    metrics["flaky_count"] = sum(
        1 for r in rows if r.layer == 1 and (r.score_detail or {}).get("flaky")
    )
    metrics["failure_clusters"] = compute_failure_clusters(rows)
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


async def get_run_diff(
    db: AsyncSession, run_id: int, *, against: int | None = None
) -> dict[str, Any] | None:
    current = await db.get(EvalRun, run_id)
    if not current:
        return None
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
    stmt = stmt.order_by(desc(EvalJudgeFeedback.created_at))
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
