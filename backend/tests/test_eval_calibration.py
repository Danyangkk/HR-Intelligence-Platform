"""Grader calibration — feedback rules and demo seed samples."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import func, select

from src.db.session import AsyncSessionLocal
from src.eval.demo_seed import delete_demo_eval_runs, seed_eval_demo, DEMO_TRIGGER
from src.models import EvalCaseResult, EvalJudgeFeedback, EvalRun
from src.services.eval_service import compute_judge_calibration, submit_judge_feedback


@pytest.mark.asyncio
async def test_demo_run_b_has_22_calibration_samples():
    async with AsyncSessionLocal() as db:
        await seed_eval_demo(db, force=True, now=datetime(2026, 6, 5, 14, 0))
        run = await db.scalar(
            select(EvalRun).where(EvalRun.trigger == DEMO_TRIGGER, EvalRun.version == "v1.4.0")
        )
        assert run is not None
        fb_count = await db.scalar(
            select(func.count())
            .select_from(EvalJudgeFeedback)
            .join(EvalCaseResult, EvalCaseResult.id == EvalJudgeFeedback.case_result_id)
            .where(EvalCaseResult.run_id == run.id)
        )
        agree = await db.scalar(
            select(func.count())
            .select_from(EvalJudgeFeedback)
            .join(EvalCaseResult, EvalCaseResult.id == EvalJudgeFeedback.case_result_id)
            .where(EvalCaseResult.run_id == run.id, EvalJudgeFeedback.verdict == "agree")
        )
        disagree = await db.scalar(
            select(func.count())
            .select_from(EvalJudgeFeedback)
            .join(EvalCaseResult, EvalCaseResult.id == EvalJudgeFeedback.case_result_id)
            .where(EvalCaseResult.run_id == run.id, EvalJudgeFeedback.verdict == "disagree")
        )
        assert fb_count == 22
        assert agree == 18
        assert disagree == 4

        cal = await compute_judge_calibration(db, run_id=run.id)
        assert cal["sample_count"] == 20  # 22 rows, 20 unique L3 case results (latest wins)
        assert cal["insufficient"] is False
        assert cal["agreement_rate"] is not None
        assert 0.82 <= cal["agreement_rate"] <= 0.88

        await delete_demo_eval_runs(db)


@pytest.mark.asyncio
async def test_demo_run_c_calibration_includes_seed_pool():
    """v1.4.1 (#407 scenario): seed 22 on v1.4.0 + 1 demo feedback → 23 samples."""
    async with AsyncSessionLocal() as db:
        await seed_eval_demo(db, force=True, now=datetime(2026, 6, 5, 14, 0))
        run_c = await db.scalar(
            select(EvalRun).where(EvalRun.trigger == DEMO_TRIGGER, EvalRun.version == "v1.4.1")
        )
        l3 = await db.scalar(
            select(EvalCaseResult).where(
                EvalCaseResult.run_id == run_c.id,
                EvalCaseResult.layer == 3,
                EvalCaseResult.case_id == "e-policy-1",
            )
        )
        await submit_judge_feedback(
            db,
            case_result_id=l3.id,
            verdict="agree",
            human_overall=None,
            note="demo session",
            created_by="tech_admin",
        )
        cal = await compute_judge_calibration(db, run_id=run_c.id)
        assert cal["sample_count"] == 21  # 20 seed (v1.4.0) + 1 demo session on v1.4.1
        assert cal["insufficient"] is False
        assert cal["agreement_rate"] is not None
        assert 0.82 <= cal["agreement_rate"] <= 0.88
        await delete_demo_eval_runs(db)


@pytest.mark.asyncio
async def test_real_run_calibration_excludes_demo_seed_pool():
    async with AsyncSessionLocal() as db:
        await seed_eval_demo(db, force=True, now=datetime(2026, 6, 5, 14, 0))
        real = EvalRun(version="real-cal", trigger="manual", status="done")
        db.add(real)
        await db.flush()
        case_row = EvalCaseResult(
            run_id=real.id,
            case_id="e-policy-1",
            layer=3,
            passed=True,
            score=4.0,
        )
        db.add(case_row)
        await db.commit()
        await submit_judge_feedback(
            db,
            case_result_id=case_row.id,
            verdict="agree",
            human_overall=None,
            note=None,
            created_by="tech_admin",
        )
        demo_cal = await compute_judge_calibration(
            db,
            run_id=(
                await db.scalar(
                    select(EvalRun.id).where(
                        EvalRun.trigger == DEMO_TRIGGER, EvalRun.version == "v1.4.1"
                    )
                )
            ),
        )
        real_cal = await compute_judge_calibration(db, run_id=real.id)
        assert demo_cal["sample_count"] == 20
        assert real_cal["sample_count"] == 1
        assert real_cal["insufficient"] is True
        await db.delete(real)
        await delete_demo_eval_runs(db)


@pytest.mark.asyncio
async def test_calibration_threshold_19_then_20_then_21():
    async with AsyncSessionLocal() as db:
        run = EvalRun(version="cal-threshold", trigger="manual", status="done")
        db.add(run)
        await db.flush()
        case_rows: list[EvalCaseResult] = []
        for i in range(21):
            row = EvalCaseResult(
                run_id=run.id,
                case_id=f"e-cal-{i}",
                layer=3,
                passed=True,
                score=4.0,
            )
            db.add(row)
            case_rows.append(row)
        await db.commit()

        for row in case_rows[:19]:
            await submit_judge_feedback(
                db,
                case_result_id=row.id,
                verdict="agree",
                human_overall=None,
                note=None,
                created_by="tech_admin",
            )
        cal19 = await compute_judge_calibration(db, run_id=run.id)
        assert cal19["sample_count"] == 19
        assert cal19["insufficient"] is True
        assert cal19["agreement_rate"] is None

        await submit_judge_feedback(
            db,
            case_result_id=case_rows[19].id,
            verdict="agree",
            human_overall=None,
            note=None,
            created_by="tech_admin",
        )
        cal20 = await compute_judge_calibration(db, run_id=run.id)
        assert cal20["sample_count"] == 20
        assert cal20["insufficient"] is False
        assert cal20["agreement_rate"] == 1.0

        await submit_judge_feedback(
            db,
            case_result_id=case_rows[20].id,
            verdict="disagree",
            human_overall=1,
            note="far off",
            created_by="tech_admin",
        )
        cal21 = await compute_judge_calibration(db, run_id=run.id)
        assert cal21["sample_count"] == 21
        assert cal21["insufficient"] is False
        assert cal21["agreement_rate"] == pytest.approx(20 / 21, rel=1e-4)

        await db.delete(run)
        await db.commit()


@pytest.mark.asyncio
async def test_demo_resubmit_updates_calibration_without_double_count():
    async with AsyncSessionLocal() as db:
        await seed_eval_demo(db, force=True, now=datetime(2026, 6, 5, 14, 0))
        run_b = await db.scalar(
            select(EvalRun).where(EvalRun.trigger == DEMO_TRIGGER, EvalRun.version == "v1.4.0")
        )
        l3 = await db.scalar(
            select(EvalCaseResult).where(
                EvalCaseResult.run_id == run_b.id,
                EvalCaseResult.layer == 3,
                EvalCaseResult.case_id == "e-cmp-1",
            )
        )
        cal_before = await compute_judge_calibration(db, run_id=run_b.id)
        assert cal_before["sample_count"] == 20

        await submit_judge_feedback(
            db,
            case_result_id=l3.id,
            verdict="disagree",
            human_overall=1,
            note="改判测试",
            created_by="tech_admin",
        )
        cal_after = await compute_judge_calibration(db, run_id=run_b.id)
        assert cal_after["sample_count"] == 20
        assert cal_after["agreement_rate"] is not None
        assert cal_after["agreement_rate"] < cal_before["agreement_rate"]

        await delete_demo_eval_runs(db)


@pytest.mark.asyncio
async def test_submit_feedback_agree_uses_judge_overall():
    async with AsyncSessionLocal() as db:
        run = EvalRun(version="cal-test", trigger="manual", status="done")
        db.add(run)
        await db.flush()
        case_row = EvalCaseResult(
            run_id=run.id,
            case_id="e-policy-1",
            layer=3,
            passed=True,
            score=4.5,
        )
        db.add(case_row)
        await db.commit()

        with pytest.raises(ValueError, match="human_overall"):
            await submit_judge_feedback(
                db,
                case_result_id=case_row.id,
                verdict="disagree",
                human_overall=None,
                note="缺引用",
                created_by="tech_admin",
            )

        fb = await submit_judge_feedback(
            db,
            case_result_id=case_row.id,
            verdict="agree",
            human_overall=None,
            note=None,
            created_by="tech_admin",
        )
        assert fb["human_overall"] == 4

        with pytest.raises(ValueError, match="feedback already submitted"):
            await submit_judge_feedback(
                db,
                case_result_id=case_row.id,
                verdict="disagree",
                human_overall=3,
                note="改判",
                created_by="tech_admin",
            )

        await db.delete(run)
        await db.commit()


@pytest.mark.asyncio
async def test_ensure_demo_seed_preserves_user_feedback():
    async with AsyncSessionLocal() as db:
        await delete_demo_eval_runs(db)
        ids1 = await seed_eval_demo(db, force=True, now=datetime(2026, 6, 5, 14, 0))
        run_c = await db.scalar(
            select(EvalRun).where(EvalRun.trigger == DEMO_TRIGGER, EvalRun.version == "v1.4.1")
        )
        l3 = await db.scalar(
            select(EvalCaseResult).where(
                EvalCaseResult.run_id == run_c.id,
                EvalCaseResult.layer == 3,
                EvalCaseResult.case_id == "e-policy-1",
            )
        )
        await submit_judge_feedback(
            db,
            case_result_id=l3.id,
            verdict="disagree",
            human_overall=2,
            note="demo user fb",
            created_by="tech_admin",
        )
        ids2 = await seed_eval_demo(db, force=False)
        assert ids2 == ids1
        fb = await db.scalar(
            select(EvalJudgeFeedback).where(EvalJudgeFeedback.case_result_id == l3.id)
        )
        assert fb is not None
        assert fb.verdict == "disagree"
        assert fb.human_overall == 2
        await delete_demo_eval_runs(db)


@pytest.mark.asyncio
async def test_force_demo_seed_clears_demo_feedback():
    async with AsyncSessionLocal() as db:
        await seed_eval_demo(db, force=True, now=datetime(2026, 6, 5, 14, 0))
        run_c = await db.scalar(
            select(EvalRun).where(EvalRun.trigger == DEMO_TRIGGER, EvalRun.version == "v1.4.1")
        )
        l3 = await db.scalar(
            select(EvalCaseResult).where(
                EvalCaseResult.run_id == run_c.id,
                EvalCaseResult.layer == 3,
                EvalCaseResult.case_id == "e-policy-1",
            )
        )
        await submit_judge_feedback(
            db,
            case_result_id=l3.id,
            verdict="agree",
            human_overall=None,
            note="will be cleared",
            created_by="tech_admin",
        )
        await seed_eval_demo(db, force=True, now=datetime(2026, 6, 5, 14, 0))
        fb = await db.scalar(
            select(EvalJudgeFeedback).where(EvalJudgeFeedback.case_result_id == l3.id)
        )
        assert fb is None
        await delete_demo_eval_runs(db)
