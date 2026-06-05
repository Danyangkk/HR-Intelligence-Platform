"""Demo eval seed — metrics consistency and story-line regression."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from src.db.session import AsyncSessionLocal
from src.eval.coverage import build_eval_coverage
from src.eval.demo_seed import (
    DEMO_TRIGGER,
    assert_demo_metrics,
    delete_demo_eval_runs,
    seed_eval_demo,
)
from src.eval.loader import load_eval_set
from src.models import EvalCaseResult, EvalRun
from src.services.eval_service import (
    build_run_metrics_from_rows,
    compute_failure_clusters,
    compute_metrics_from_case_rows,
    get_run_cases_payload,
    get_run_diff,
)


def _assert_metrics_derivable(rows, payload_metrics, run):
    direct = compute_metrics_from_case_rows(rows)
    assert payload_metrics["assertion"] == direct["assertion"]
    assert payload_metrics["grader_avg"] == direct["grader_avg"]
    assert payload_metrics["gate_passed"] == direct["gate_passed"]
    assert payload_metrics["planner_accuracy"] == direct["planner_accuracy"]
    assert payload_metrics["weakest_link"] == direct["weakest_link"]
    clusters = compute_failure_clusters(rows)
    if clusters:
        assert payload_metrics["weakest_link"] == clusters[0]["label"]
    else:
        assert payload_metrics["weakest_link"] == "无失败"
    assert "judge" not in payload_metrics["weakest_link"].lower()


@pytest.mark.asyncio
async def test_demo_seed_metrics_match_case_rows():
    async with AsyncSessionLocal() as db:
        await seed_eval_demo(db, force=True, now=datetime(2026, 6, 5, 14, 0))
        runs = (
            await db.execute(select(EvalRun).where(EvalRun.trigger == DEMO_TRIGGER))
        ).scalars().all()
        assert len(runs) == 4
        for run in runs:
            rows = (
                await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == run.id))
            ).scalars().all()
            payload = await get_run_cases_payload(db, run.id)
            assert payload is not None
            _assert_metrics_derivable(rows, payload["metrics"], run)
            built = await build_run_metrics_from_rows(db, run.id, rows)
            assert built["weakest_link"] == payload["metrics"]["weakest_link"]
            assert_demo_metrics(run, rows)
        await delete_demo_eval_runs(db)


@pytest.mark.asyncio
async def test_demo_run_c_weakest_is_planner_policy():
    async with AsyncSessionLocal() as db:
        await seed_eval_demo(db, force=True, now=datetime(2026, 6, 5, 14, 0))
        run = await db.scalar(
            select(EvalRun).where(EvalRun.trigger == DEMO_TRIGGER, EvalRun.version == "v1.4.1")
        )
        assert run is not None
        rows = (
            await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == run.id))
        ).scalars().all()
        metrics = compute_metrics_from_case_rows(rows)
        assert metrics["weakest_link"] == "planner · policy"
        failed_agg = [r for r in rows if r.case_id.startswith("e-agg") and not r.passed]
        assert not failed_agg, "aggregate cases should all pass in Run C"
        await delete_demo_eval_runs(db)


@pytest.mark.asyncio
async def test_demo_run_b_regression_story():
    async with AsyncSessionLocal() as db:
        await seed_eval_demo(db, force=True, now=datetime(2026, 6, 5, 14, 0))
        runs = {r.version: r for r in (await db.execute(select(EvalRun).where(EvalRun.trigger == DEMO_TRIGGER))).scalars()}
        base = runs["v1.3.0-基线"]
        reg = runs["v1.4.0"]
        fix = runs["v1.4.1"]
        diff_b = await get_run_diff(db, reg.id, against=base.id)
        assert len(diff_b["regressed"]) == 3, diff_b["regressed"]
        assert set(diff_b["fixed"]) == {"e-agg-2"}, diff_b["fixed"]
        rows_b = (
            await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == reg.id))
        ).scalars().all()
        metrics_b = compute_metrics_from_case_rows(rows_b)
        assert metrics_b["gate_passed"] is False
        assert metrics_b["planner_accuracy"] == 0.8667
        assert metrics_b["grader_avg"] == 4.1
        assert metrics_b["weakest_link"] == diff_b["failure_clusters"][0]["label"]
        diff_c = await get_run_diff(db, fix.id, against=reg.id)
        for cid in diff_b["regressed"]:
            assert cid in diff_c["fixed"]
        await delete_demo_eval_runs(db)


def test_coverage_metric_callouts_not_required_for_list():
    data = build_eval_coverage()
    missing_mc = data["completeness"]["missing"]["metric_callouts"]
    assert "e-list-1" not in missing_mc


def test_all_demo_cases_have_expected_snapshots():
    cases = load_eval_set()
    assert len(cases) == 30
