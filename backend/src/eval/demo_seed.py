"""Demo eval runs for 评测中心 presentation — baseline → regression → fix story."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.eval.loader import load_eval_set
from src.models import EvalCaseResult, EvalJudgeFeedback, EvalRun
from src.services.eval_service import compute_metrics_from_case_rows

DEMO_TRIGGER = "demo"

# Layer pass/fail overrides per run (case_id → set of failing layers)
RUN_A_L1_FAIL = frozenset({"e-policy-1", "e-agg-2"})
RUN_A_L2_FAIL = frozenset({"e-policy-1"})

RUN_B_L1_FAIL = frozenset({"e-policy-1", "e-lookup-1", "e-list-1", "e-cmp-1"})
RUN_B_L2_FAIL = frozenset({"e-lookup-1", "e-list-1", "e-cmp-1", "e-policy-1"})

RUN_C_L1_FAIL = frozenset({"e-policy-1"})  # 29/30 → gate pass

FLAKY_CASE = "e-lookup-1"
L3_VIOLATIONS_CASE = "e-agg-4"
L3_RICH_CASES = ("e-policy-1", "e-agg-1")

RUN_A_L3_LOW = frozenset({"e-fc-1", "e-attr-4", "e-lookup-2", "e-agg-3"})
RUN_A_L3_SCORES: dict[str, float] = {}
RUN_B_L3_SCORES: dict[str, float] = {}
RUN_C_L3_SCORES: dict[str, float] = {}


def _init_l3_score_maps() -> None:
    if RUN_A_L3_SCORES:
        return
    l3_ids = [c["id"] for c in load_eval_set() if 3 in (c.get("layer") or [])]
    # Run A target avg 4.4 → sum 88
    for cid in l3_ids:
        RUN_A_L3_SCORES[cid] = 4.0 if cid in RUN_A_L3_LOW else 4.5
    for cid in l3_ids:
        if cid in {"e-lookup-1", "e-list-1", "e-cmp-1", "e-policy-1"}:
            RUN_B_L3_SCORES[cid] = 3.0
        else:
            RUN_B_L3_SCORES[cid] = 4.375
    # Run C target avg 4.5 → sum 90
    for cid in l3_ids:
        RUN_C_L3_SCORES[cid] = 4.0 if cid == "e-policy-1" else 4.53


@dataclass
class DemoRunSpec:
    version: str
    started_at: datetime
    layers: frozenset[int]
    l1_fail: frozenset[str] = frozenset()
    l2_fail: frozenset[str] = frozenset()
    l3_scores: dict[str, float] = field(default_factory=dict)
    duration_ms: int = 120_000
    seed_feedback: bool = False
    l3_showcase_violations: bool = False


def _expected_snapshot(case: dict[str, Any]) -> dict[str, Any]:
    return dict(case.get("expected") or {})


def _trace_id(case_id: str) -> str:
    return f"demo-trace-{case_id}"


def _l1_actual(case: dict[str, Any], *, fail: bool) -> tuple[dict[str, Any], dict[str, Any] | None]:
    exp = _expected_snapshot(case)
    if not fail:
        return {
            "intent": exp.get("intent"),
            "rejected": bool(exp.get("reject")),
            "clarify": bool(exp.get("clarify_or_inherit")),
            "chitchat": bool(exp.get("chitchat")),
            "agent_run_id": _trace_id(case["id"]),
        }, None
    if case["id"] == "e-policy-1":
        wrong = "lookup"
        detail = {"mismatches": [f"intent expected policy, got {wrong}"]}
        actual = {
            "intent": wrong,
            "rejected": False,
            "clarify": False,
            "agent_run_id": _trace_id(case["id"]),
        }
        return actual, detail
    wrong = "aggregate"
    exp_intent = exp.get("intent") or "unknown"
    detail = {"mismatches": [f"intent expected {exp_intent}, got {wrong}"]}
    return {
        "intent": wrong,
        "rejected": False,
        "clarify": False,
        "agent_run_id": _trace_id(case["id"]),
    }, detail


def _l2_actual(case: dict[str, Any], *, fail: bool) -> tuple[dict[str, Any], dict[str, Any] | None]:
    exp = _expected_snapshot(case)
    mods = list(exp.get("expected_modules") or [])
    docs = list(exp.get("expected_doc_chunks") or [])
    if not fail:
        return {
            "modules": mods,
            "doc_chunks": docs,
            "agent_run_id": _trace_id(case["id"]),
        }, None
    detail: dict[str, Any] = {}
    if mods:
        detail["missing_modules"] = [f"expected module not hit: {mods[0]}"]
    if docs:
        detail["missing_doc_chunks"] = list(docs)
    elif mods:
        detail["missing_doc_chunks"] = []
    return {"modules": [], "doc_chunks": [], "agent_run_id": _trace_id(case["id"])}, detail


def _l3_content(case: dict[str, Any], score: float, *, showcase_violations: bool = False) -> dict[str, Any]:
    exp = _expected_snapshot(case)
    cid = case["id"]
    detail = {
        "correctness": min(5.0, score + 0.2),
        "completeness": max(1.0, score - 0.3),
        "citation": score,
        "compliance": min(5.0, score + 0.1),
    }
    points = exp.get("answer_points") or ["回答覆盖核心要点"]
    answer = "；".join(str(p) for p in points[:4])
    if cid == "e-policy-1":
        answer = (
            "根据员工手册第4.2条：满1年5天、满10年10天年休假；"
            "可顺延至次年一季度；离职按月折算。"
        )
    citations = exp.get("expected_citations") or [{"kind": "doc", "name": "员工手册", "seq": "4.2"}]
    violations: list[str] = []
    reasoning = (
        f"答案覆盖 {len(points)} 条要点，引用与口径基本符合 rubric。"
        f" overall={score:.1f}。"
    )
    if cid == L3_VIOLATIONS_CASE and showcase_violations:
        violations = ["出现个人薪资金额，违反 forbid 红线"]
        reasoning = "聚合回答中泄露个人薪资明细，compliance 维度不达标。"
        detail["compliance"] = 2.0
    return {
        "score": score,
        "score_detail": detail,
        "actual": {
            "answer": answer,
            "answer_preview": answer[:120],
            "citations": citations,
            "agent_run_id": _trace_id(cid),
        },
        "judge_reasoning": reasoning,
        "violations": violations,
        "passed": score >= 4.0,
    }


def _build_case_rows(
    case: dict[str, Any],
    *,
    layers: frozenset[int],
    l1_fail: frozenset[str],
    l2_fail: frozenset[str],
    l3_scores: dict[str, float],
    l3_showcase_violations: bool = False,
) -> list[dict[str, Any]]:
    cid = case["id"]
    declared = frozenset(case.get("layer") or [1])
    rows: list[dict[str, Any]] = []
    exp = _expected_snapshot(case)

    if 1 in layers and 1 in declared:
        fail = cid in l1_fail
        actual, detail = _l1_actual(case, fail=fail)
        row: dict[str, Any] = {
            "case_id": cid,
            "layer": 1,
            "passed": not fail,
            "expected": exp,
            "actual": actual,
            "score_detail": detail,
        }
        if cid == FLAKY_CASE:
            row["score_detail"] = {**(detail or {}), "flaky": True}
        rows.append(row)

    if 2 in layers and 2 in declared:
        fail = cid in l2_fail
        actual, detail = _l2_actual(case, fail=fail)
        rows.append(
            {
                "case_id": cid,
                "layer": 2,
                "passed": not fail,
                "expected": exp,
                "actual": actual,
                "score_detail": detail,
            }
        )

    if 3 in layers and 3 in declared:
        score = l3_scores.get(cid, 4.5)
        l3 = _l3_content(case, score, showcase_violations=l3_showcase_violations)
        rows.append(
            {
                "case_id": cid,
                "layer": 3,
                "passed": l3["passed"],
                "score": l3["score"],
                "score_detail": l3["score_detail"],
                "expected": exp,
                "actual": l3["actual"],
                "judge_reasoning": l3["judge_reasoning"],
                "violations": l3["violations"],
            }
        )

    return rows


def _demo_run_specs(now: datetime | None = None) -> list[DemoRunSpec]:
    _init_l3_score_maps()
    base = now or datetime.now()
    mmdd = base.strftime("%m%d")
    return [
        DemoRunSpec(
            version="v1.3.0-基线",
            started_at=base - timedelta(days=3, hours=-2),
            layers=frozenset({1, 2, 3}),
            l1_fail=RUN_A_L1_FAIL,
            l2_fail=RUN_A_L2_FAIL,
            l3_scores=RUN_A_L3_SCORES,
            duration_ms=480_000,
            l3_showcase_violations=True,
        ),
        DemoRunSpec(
            version="v1.4.0",
            started_at=base - timedelta(days=1, hours=3),
            layers=frozenset({1, 2, 3}),
            l1_fail=RUN_B_L1_FAIL,
            l2_fail=RUN_B_L2_FAIL,
            l3_scores=RUN_B_L3_SCORES,
            duration_ms=510_000,
            seed_feedback=True,
        ),
        DemoRunSpec(
            version="v1.4.1",
            started_at=base - timedelta(hours=4),
            layers=frozenset({1, 2, 3}),
            l1_fail=RUN_C_L1_FAIL,
            l2_fail=frozenset(),
            l3_scores=RUN_C_L3_SCORES,
            duration_ms=495_000,
        ),
        DemoRunSpec(
            version=f"{mmdd} 快速检查",
            started_at=base - timedelta(hours=1),
            layers=frozenset({1}),
            l1_fail=RUN_B_L1_FAIL,
            duration_ms=28_000,
        ),
    ]


def _sync_run_aggregates(run: EvalRun, rows: list[EvalCaseResult]) -> None:
    l1 = [r for r in rows if r.layer == 1]
    l2 = [r for r in rows if r.layer == 2]
    l3 = [r for r in rows if r.layer == 3]
    scored = [r for r in l3 if r.score is not None]
    run.layer1_total = len(l1)
    run.layer1_pass = sum(1 for r in l1 if r.passed)
    run.layer2_total = len(l2)
    run.layer2_pass = sum(1 for r in l2 if r.passed)
    run.layer3_total = len(l3)
    run.layer3_scored = len(scored)
    if scored:
        run.layer3_avg = round(sum(float(r.score) for r in scored) / len(scored), 2)
    else:
        run.layer3_avg = None


def _seed_feedback(rows: list[EvalCaseResult]) -> list[EvalJudgeFeedback]:
    l3_rows = [r for r in rows if r.layer == 3 and r.score is not None]
    feedbacks: list[EvalJudgeFeedback] = []
    # 22 samples: 18 agree + 4 disagree (2 cases get an extra agree for count)
    for i, row in enumerate(l3_rows):
        human = int(round(float(row.score)))
        verdict = "agree"
        if i < 4:
            verdict = "disagree"
            rounded = int(round(float(row.score)))
            # 最后 1 条 disagree 人工分距 judge ≤1，使演示校准率落在 0.82–0.88
            human = max(1, rounded - (1 if i == 3 else 2))
        feedbacks.append(
            EvalJudgeFeedback(
                case_result_id=row.id,
                verdict=verdict,
                human_overall=human,
                note="demo seed" if verdict == "agree" else "demo 人工校准样本",
                created_by="tech_admin",
            )
        )
    # 2 extra agree samples on first cases to reach 22
    for row in l3_rows[:2]:
        feedbacks.append(
            EvalJudgeFeedback(
                case_result_id=row.id,
                verdict="agree",
                human_overall=int(round(float(row.score))),
                note="demo seed extra",
                created_by="tech_admin",
            )
        )
    return feedbacks


async def delete_demo_eval_runs(db: AsyncSession) -> int:
    demo_ids = (
        await db.execute(select(EvalRun.id).where(EvalRun.trigger == DEMO_TRIGGER))
    ).scalars().all()
    if not demo_ids:
        return 0
    await db.execute(delete(EvalRun).where(EvalRun.id.in_(demo_ids)))
    await db.commit()
    return len(demo_ids)


async def seed_eval_demo(
    db: AsyncSession, *, force: bool = False, now: datetime | None = None
) -> list[int]:
    """Ensure or refresh demo eval runs. Returns run ids.

    force=False (default): create demo runs only when missing; never clears feedback.
    force=True: delete all demo runs (and their feedback) then recreate from seed.
    Non-demo runs are never touched.
    """
    existing = (
        await db.execute(
            select(EvalRun.id)
            .where(EvalRun.trigger == DEMO_TRIGGER)
            .order_by(EvalRun.id)
        )
    ).scalars().all()
    if existing and not force:
        return list(existing)

    await delete_demo_eval_runs(db)
    cases = load_eval_set()
    created_ids: list[int] = []

    for spec in _demo_run_specs(now):
        finished = spec.started_at + timedelta(milliseconds=spec.duration_ms)
        profile = "layer1_only" if spec.layers == frozenset({1}) else "full"
        run = EvalRun(
            version=spec.version,
            trigger=DEMO_TRIGGER,
            triggered_by="demo_seed",
            status="done",
            started_at=spec.started_at,
            finished_at=finished,
            duration_ms=spec.duration_ms,
            total_cases=len(cases),
            notes=profile,
        )
        db.add(run)
        await db.flush()

        result_rows: list[EvalCaseResult] = []
        for case in cases:
            for payload in _build_case_rows(
                case,
                layers=spec.layers,
                l1_fail=spec.l1_fail,
                l2_fail=spec.l2_fail,
                l3_scores=spec.l3_scores,
                l3_showcase_violations=spec.l3_showcase_violations,
            ):
                row = EvalCaseResult(run_id=run.id, **payload)
                db.add(row)
                result_rows.append(row)
        await db.flush()
        _sync_run_aggregates(run, result_rows)
        if spec.seed_feedback:
            for fb in _seed_feedback(result_rows):
                db.add(fb)
        created_ids.append(run.id)

    await db.commit()
    return created_ids


def assert_demo_metrics(run: EvalRun, rows: list[EvalCaseResult]) -> None:
    """Hard assertion: card metrics must match case rows exactly."""
    metrics = compute_metrics_from_case_rows(rows)
    targets: dict[str, dict[str, Any]] = {
        "v1.3.0-基线": {
            "planner_accuracy": 0.9333,
            "gate_passed": True,
            "grader_avg": 4.4,
        },
        "v1.4.0": {
            "planner_accuracy": 0.8667,
            "gate_passed": False,
            "grader_avg": 4.1,
        },
        "v1.4.1": {
            "gate_passed": True,
            "grader_avg": 4.5,
        },
    }
    t = targets.get(run.version)
    if not t:
        return
    if "planner_accuracy" in t:
        assert metrics["planner_accuracy"] == t["planner_accuracy"], run.version
    if "gate_passed" in t:
        assert metrics["gate_passed"] is t["gate_passed"], run.version
    if "grader_avg" in t and metrics["grader_avg"] is not None:
        assert abs(metrics["grader_avg"] - t["grader_avg"]) < 0.011, (
            f"{run.version} grader_avg {metrics['grader_avg']} != {t['grader_avg']}"
        )
