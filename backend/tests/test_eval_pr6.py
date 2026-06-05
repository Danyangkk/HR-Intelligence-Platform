from __future__ import annotations

from datetime import datetime

import pytest

from src.db.session import AsyncSessionLocal
from src.eval.coverage import build_eval_coverage
from src.eval.version import get_default_eval_version, is_garbage_eval_version, normalize_eval_version
from src.models import EvalCaseResult, EvalRun
from src.services.eval_service import (
    compute_judge_calibration,
    compute_metrics_from_case_rows,
    delete_garbage_eval_runs,
    get_run_diff,
    list_run_cases,
    submit_judge_feedback,
)

EVAL_TEST_VERSION = "pytest"


@pytest.fixture
async def eval_run_ids():
    """Collect eval run ids created in a test and delete them after."""
    ids: list[int] = []
    yield ids
    if not ids:
        return
    async with AsyncSessionLocal() as db:
        for run_id in ids:
            row = await db.get(EvalRun, run_id)
            if row:
                await db.delete(row)
        await db.commit()


def test_build_eval_coverage_matrix():
    data = build_eval_coverage()
    assert data["total_cases"] >= 30
    assert "chitchat" in data["matrix"]
    assert "L1" in data["matrix"]["chitchat"]
    assert isinstance(data["completeness"]["missing"]["answer_points"], list)
    assert "groups" in data["completeness"]
    assert "e-list-1" not in data["completeness"]["missing"]["metric_callouts"]


def test_eval_version_normalization():
    fixed = datetime(2026, 6, 5, 11, 38)
    assert get_default_eval_version(fixed) == "0605-1138"
    assert normalize_eval_version(None, now=fixed) == "0605-1138"
    assert normalize_eval_version("", now=fixed) == "0605-1138"
    assert normalize_eval_version("v1.4.0", now=fixed) == "v1.4.0"
    assert is_garbage_eval_version("t")
    assert is_garbage_eval_version("base")
    assert not is_garbage_eval_version(EVAL_TEST_VERSION)


@pytest.mark.asyncio
async def test_run_diff_regressed_and_clusters(eval_run_ids):
    async with AsyncSessionLocal() as db:
        base = EvalRun(version=EVAL_TEST_VERSION, trigger="manual", status="done", total_cases=1)
        cur = EvalRun(version=EVAL_TEST_VERSION, trigger="manual", status="done", total_cases=1)
        db.add_all([base, cur])
        await db.flush()
        eval_run_ids.extend([base.id, cur.id])
        db.add_all(
            [
                EvalCaseResult(
                    run_id=base.id,
                    case_id="e-policy-1",
                    layer=1,
                    passed=True,
                    expected={"intent": "policy"},
                ),
                EvalCaseResult(
                    run_id=cur.id,
                    case_id="e-policy-1",
                    layer=1,
                    passed=False,
                    expected={"intent": "policy"},
                    actual={"intent": "lookup"},
                    score_detail={"mismatches": ["intent expected policy, got lookup"]},
                ),
                EvalCaseResult(
                    run_id=cur.id,
                    case_id="e-policy-1",
                    layer=2,
                    passed=False,
                    expected={"intent": "policy"},
                ),
            ]
        )
        await db.commit()

        diff = await get_run_diff(db, cur.id, against=base.id)
        assert diff is not None
        assert "e-policy-1" in diff["regressed"]
        assert diff["failure_clusters"]
        assert diff["failure_clusters"][0]["stage"] in {"planner", "retrieve", "answer"}
        assert "judge" not in diff["failure_clusters"][0]["label"].lower()


@pytest.mark.asyncio
async def test_compute_metrics_from_case_rows():
    rows = [
        EvalCaseResult(run_id=1, case_id="a", layer=1, passed=True),
        EvalCaseResult(run_id=1, case_id="a", layer=2, passed=False),
        EvalCaseResult(run_id=1, case_id="b", layer=3, passed=True, score=4.0),
        EvalCaseResult(run_id=1, case_id="c", layer=3, passed=True, score=5.0),
    ]
    metrics = compute_metrics_from_case_rows(rows)
    assert metrics["assertion"] == {"passed": 1, "total": 2}
    assert metrics["grader_avg"] == 4.5
    assert metrics["grader_scored_count"] == 2
    assert metrics["gate_status"] == "ok"
    assert metrics["gate_passed"] is True


@pytest.mark.asyncio
async def test_list_run_cases_failed_first_and_metrics(eval_run_ids):
    async with AsyncSessionLocal() as db:
        run = EvalRun(version=EVAL_TEST_VERSION, trigger="manual", status="done", total_cases=1)
        db.add(run)
        await db.flush()
        eval_run_ids.append(run.id)
        db.add_all(
            [
                EvalCaseResult(run_id=run.id, case_id="e-chat-1", layer=1, passed=True),
                EvalCaseResult(run_id=run.id, case_id="e-policy-1", layer=1, passed=False),
                EvalCaseResult(run_id=run.id, case_id="e-policy-1", layer=3, passed=True, score=4.5),
            ]
        )
        await db.commit()
        payload = await list_run_cases(db, run.id)
        assert payload is not None
        assert payload["items"][0]["passed"] is False
        assert payload["items"][0]["query"]
        assert payload["metrics"]["assertion"]["total"] == 2
        assert payload["metrics"]["grader_avg"] == 4.5


@pytest.mark.asyncio
async def test_submit_judge_feedback_and_calibration_insufficient(eval_run_ids):
    async with AsyncSessionLocal() as db:
        run = EvalRun(version=EVAL_TEST_VERSION, trigger="manual", status="done", total_cases=1)
        db.add(run)
        await db.flush()
        eval_run_ids.append(run.id)
        case_row = EvalCaseResult(
            run_id=run.id,
            case_id="e-policy-1",
            layer=3,
            passed=True,
            score=4.5,
            judge_reasoning="ok",
        )
        db.add(case_row)
        await db.commit()

        fb = await submit_judge_feedback(
            db,
            case_result_id=case_row.id,
            verdict="disagree",
            human_overall=4,
            note="缺引用",
            created_by="tech_admin",
        )
        assert fb["verdict"] == "disagree"
        assert fb["human_overall"] == 4

        cal = await compute_judge_calibration(db, run_id=run.id)
        assert cal["sample_count"] == 1
        assert cal["insufficient"] is True
        assert cal["agreement_rate"] is None


@pytest.mark.asyncio
async def test_delete_garbage_eval_runs(eval_run_ids):
    async with AsyncSessionLocal() as db:
        good = EvalRun(version=EVAL_TEST_VERSION, trigger="manual", status="done")
        bad = EvalRun(version="t", trigger="manual", status="done")
        db.add_all([good, bad])
        await db.commit()
        eval_run_ids.append(good.id)
        bad_id = bad.id
        good_id = good.id
        deleted = await delete_garbage_eval_runs(db)
        assert deleted >= 1
        assert await db.get(EvalRun, bad_id) is None
        assert await db.get(EvalRun, good_id) is not None


@pytest.mark.asyncio
async def test_submit_feedback_rejects_non_layer3(eval_run_ids):
    async with AsyncSessionLocal() as db:
        run = EvalRun(version=EVAL_TEST_VERSION, trigger="manual", status="done")
        db.add(run)
        await db.flush()
        eval_run_ids.append(run.id)
        row = EvalCaseResult(run_id=run.id, case_id="e-chat-1", layer=1, passed=True)
        db.add(row)
        await db.commit()
        with pytest.raises(ValueError, match="layer 3"):
            await submit_judge_feedback(
                db,
                case_result_id=row.id,
                verdict="agree",
                human_overall=4,
                note=None,
                created_by="tech_admin",
            )
