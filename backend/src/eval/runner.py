"""Eval 跑批 orchestrator — 一键跑完 eval_set.yaml。

run_type:
  full      — L1+L2+L3（含 judge）
  l1_smoke  — 仅 L1
  gate      — L1+L2 + 基线 diff，不跑 L3
"""
from __future__ import annotations

import asyncio
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.graph import run_agent
from src.eval.baseline import get_released_baseline_run_id
from src.eval.layer1 import judge_layer1, run_planner_for_case
from src.eval.layer1_5 import judge_plan_compliance
from src.eval.layer2 import collect_actual_retrieval, judge_layer2
from src.eval.layer3 import judge_layer3
from src.eval.loader import get_case_intent, load_eval_set
from src.eval.set_version import get_eval_set_version, get_pipeline_version
from src.eval.version import normalize_eval_version
from src.models import EvalCaseResult, EvalRun
from src.services.eval_service import (
    apply_gate_diff_to_results,
    compute_gate_verdict,
)

RUN_TYPES = frozenset({"full", "l1_smoke", "gate"})


def _normalize_run_type(run_type: str | None, *, only_layer1: bool = False) -> str:
    if only_layer1:
        return "l1_smoke"
    rt = (run_type or "full").strip()
    return rt if rt in RUN_TYPES else "full"


async def create_eval_run(
    db: AsyncSession,
    *,
    version: str = "dev",
    trigger: str = "manual",
    triggered_by: str | None = None,
    case_limit: int | None = None,
    run_type: str = "full",
    source_ticket_id: int | None = None,
    baseline_run_id: int | None = None,
) -> int:
    cases = load_eval_set()
    if case_limit:
        cases = cases[:case_limit]
    rt = _normalize_run_type(run_type)
    run = EvalRun(
        version=normalize_eval_version(version),
        trigger=trigger,
        triggered_by=triggered_by,
        status="running",
        total_cases=len(cases),
        run_type=rt,
        source_ticket_id=source_ticket_id,
        baseline_run_id=baseline_run_id,
        eval_set_version=get_eval_set_version(),
        notes="layer1_only" if rt == "l1_smoke" else ("gate" if rt == "gate" else "full"),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run.id


async def run_eval_batch(
    db: AsyncSession,
    *,
    run_id: int | None = None,
    version: str = "dev",
    trigger: str = "manual",
    triggered_by: str | None = None,
    only_layer1: bool = False,
    run_type: str | None = None,
    source_ticket_id: int | None = None,
    baseline_run_id: int | None = None,
    new_case_ids: list[str] | None = None,
    case_limit: int | None = None,
) -> int:
    rt = _normalize_run_type(run_type, only_layer1=only_layer1)
    cases = load_eval_set()
    if case_limit:
        cases = cases[:case_limit]

    if run_id:
        run = await db.get(EvalRun, run_id)
        if not run:
            raise ValueError(f"eval run {run_id} not found")
        run.status = "running"
        run.total_cases = len(cases)
        run.run_type = rt
        if baseline_run_id is not None:
            run.baseline_run_id = baseline_run_id
        if source_ticket_id is not None:
            run.source_ticket_id = source_ticket_id
        run.eval_set_version = get_eval_set_version()
        await db.commit()
    else:
        if rt == "gate" and baseline_run_id is None:
            baseline_run_id = await get_released_baseline_run_id(db)
        run = EvalRun(
            version=normalize_eval_version(version),
            trigger=trigger,
            triggered_by=triggered_by,
            status="running",
            total_cases=len(cases),
            run_type=rt,
            source_ticket_id=source_ticket_id,
            baseline_run_id=baseline_run_id,
            eval_set_version=get_eval_set_version(),
            notes="layer1_only" if rt == "l1_smoke" else ("gate" if rt == "gate" else "full"),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

    started = time.perf_counter()
    layer1_total = layer1_pass = 0
    layer15_total = layer15_pass = 0
    layer2_total = layer2_pass = 0
    layer3_total = layer3_scored = 0
    rubric_sums = {"correctness": 0.0, "completeness": 0.0, "citation": 0.0, "compliance": 0.0}
    overall_sum = 0.0
    intent_results: dict[str, list[float]] = {}
    case_outcomes: dict[str, bool] = {}

    for case in cases:
        outcome = await _eval_one_case(
            db,
            run_id=run.id,
            case=case,
            run_type=rt,
            layer1_total=layer1_total,
            layer1_pass=layer1_pass,
            layer15_total=layer15_total,
            layer15_pass=layer15_pass,
            layer2_total=layer2_total,
            layer2_pass=layer2_pass,
            layer3_total=layer3_total,
            layer3_scored=layer3_scored,
            rubric_sums=rubric_sums,
            overall_sum=overall_sum,
            intent_results=intent_results,
        )
        layer1_total, layer1_pass, layer15_total, layer15_pass = outcome["layer1"]
        layer2_total, layer2_pass = outcome["layer2"]
        layer3_total, layer3_scored = outcome["layer3"]
        overall_sum = outcome["overall_sum"]
        case_outcomes[case["id"]] = outcome["case_passed"]

    flaky_overrides: dict[str, tuple[int, int]] = {}
    if rt == "gate":
        flaky_overrides = await _apply_gate_flaky_retries(
            db, run_id=run.id, cases=cases, case_outcomes=case_outcomes, run_type=rt
        )
        # Re-count layer metrics after flaky adjustments
        rows = (
            await db.execute(select(EvalCaseResult).where(EvalCaseResult.run_id == run.id))
        ).scalars().all()
        layer1_total = sum(1 for r in rows if r.layer == 1)
        layer1_pass = sum(1 for r in rows if r.layer == 1 and r.passed)
        layer2_total = sum(1 for r in rows if r.layer == 2)
        layer2_pass = sum(1 for r in rows if r.layer == 2 and r.passed)

    duration_ms = int((time.perf_counter() - started) * 1000)
    layer3_avg = overall_sum / layer3_scored if layer3_scored else None
    rubric_avg = {k: (v / layer3_scored if layer3_scored else None) for k, v in rubric_sums.items()}
    intent_breakdown = {
        intent: {"count": len(scores), "avg": round(sum(scores) / len(scores), 3)}
        for intent, scores in intent_results.items()
    }
    weakness = _compute_weakness(
        layer1_total,
        layer1_pass,
        intent_breakdown,
        rubric_avg,
        layer15_total=layer15_total,
        layer15_pass=layer15_pass,
    )

    run = await db.get(EvalRun, run.id)
    run.status = "done"
    run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    run.duration_ms = duration_ms
    run.layer1_total = layer1_total
    run.layer1_pass = layer1_pass
    run.layer2_total = layer2_total
    run.layer2_pass = layer2_pass
    run.layer3_total = layer3_total
    run.layer3_scored = layer3_scored
    run.layer3_avg = layer3_avg
    run.layer3_correctness_avg = rubric_avg["correctness"]
    run.layer3_completeness_avg = rubric_avg["completeness"]
    run.layer3_citation_avg = rubric_avg["citation"]
    run.layer3_compliance_avg = rubric_avg["compliance"]
    run.total_score = layer3_avg
    run.intent_breakdown = intent_breakdown
    run.weakness_summary = weakness
    run.notes = run.notes or ("layer1_only" if rt == "l1_smoke" else ("gate" if rt == "gate" else "full"))

    if rt == "gate":
        await apply_gate_diff_to_results(
            db,
            run.id,
            baseline_run_id=run.baseline_run_id,
            new_case_ids=new_case_ids,
            flaky_overrides=flaky_overrides,
        )
        verdict, _detail = await compute_gate_verdict(
            db, run, new_case_ids=new_case_ids
        )
        run.gate_verdict = verdict

    await db.commit()
    return run.id


async def _eval_one_case(
    db: AsyncSession,
    *,
    run_id: int,
    case: dict[str, Any],
    run_type: str,
    layer1_total: int,
    layer1_pass: int,
    layer15_total: int,
    layer15_pass: int,
    layer2_total: int,
    layer2_pass: int,
    layer3_total: int,
    layer3_scored: int,
    rubric_sums: dict[str, float],
    overall_sum: float,
    intent_results: dict[str, list[float]],
    replace_existing: bool = False,
) -> dict[str, Any]:
    if replace_existing:
        await db.execute(
            delete(EvalCaseResult).where(
                EvalCaseResult.run_id == run_id,
                EvalCaseResult.case_id == case["id"],
            )
        )
        await db.commit()

    case_id = case["id"]
    expected_intent = get_case_intent(case)
    case_layers = set(case.get("layer") or [1])
    if run_type == "l1_smoke":
        case_layers = {1}
    elif run_type == "gate":
        case_layers = {x for x in case_layers if x in {1, 2, 15}}
        if not case_layers:
            case_layers = {1, 2}

    planner_state: dict[str, Any] = {}
    layer1_result = {"passed": False, "actual": None, "mismatches": ["planner_call_failed"]}
    try:
        planner_state = await asyncio.to_thread(run_planner_for_case, case)
        layer1_result = judge_layer1(case, planner_state)
    except Exception as exc:  # noqa: BLE001
        layer1_result = {
            "passed": False,
            "actual": None,
            "mismatches": [f"planner_exception: {exc}"],
            "error": traceback.format_exc(limit=3),
        }

    await _record_case(
        db,
        run_id=run_id,
        case_id=case_id,
        layer=1,
        passed=layer1_result["passed"],
        expected=case.get("expected"),
        actual=layer1_result.get("actual"),
        error=layer1_result.get("error"),
        score_detail={"mismatches": layer1_result.get("mismatches") or []},
    )
    layer1_total += 1
    if layer1_result["passed"]:
        layer1_pass += 1

    layer15_result = judge_plan_compliance(planner_state)
    if not layer15_result.get("skipped"):
        layer15_total += 1
        if layer15_result["passed"]:
            layer15_pass += 1
    if 15 in case_layers or run_type != "l1_smoke":
        await _record_case(
            db,
            run_id=run_id,
            case_id=case_id,
            layer=15,
            passed=layer15_result["passed"],
            expected={"invariants": "I1-I7"},
            actual=layer15_result.get("actual"),
            score_detail={"skipped": layer15_result.get("skipped"), "reason": layer15_result.get("reason")},
        )

    need_full = bool(case_layers & {2, 3})
    if run_type == "gate":
        need_full = bool(case_layers & {2})
    if not need_full:
        case_passed = layer1_result["passed"]
        return {
            "layer1": (layer1_total, layer1_pass, layer15_total, layer15_pass),
            "layer2": (layer2_total, layer2_pass),
            "layer3": (layer3_total, layer3_scored),
            "overall_sum": overall_sum,
            "case_passed": case_passed,
        }

    if planner_state.get("rejected") and not case.get("expected", {}).get("intent"):
        case_passed = layer1_result["passed"]
        return {
            "layer1": (layer1_total, layer1_pass, layer15_total, layer15_pass),
            "layer2": (layer2_total, layer2_pass),
            "layer3": (layer3_total, layer3_scored),
            "overall_sum": overall_sum,
            "case_passed": case_passed,
        }

    full_state: dict[str, Any] = {}
    full_err: str | None = None
    try:
        full_state = await _run_full_flow(db, case)
    except Exception as exc:  # noqa: BLE001
        full_err = f"agent_run_failed: {exc}"

    l2_passed = True
    if 2 in case_layers:
        layer2_total += 1
        if full_err:
            l2_passed = False
            await _record_case(
                db, run_id=run_id, case_id=case_id, layer=2,
                passed=False, expected=case.get("expected"), actual=None, error=full_err,
            )
        else:
            try:
                actual_retrieval = await collect_actual_retrieval(db, full_state)
                l2 = judge_layer2(case, actual_retrieval)
                l2_passed = l2["passed"]
                if l2["passed"]:
                    layer2_pass += 1
                actual = dict(l2["actual"])
                actual["agent_run_id"] = full_state.get("agent_run_id")
                await _record_case(
                    db, run_id=run_id, case_id=case_id, layer=2,
                    passed=l2["passed"],
                    expected=case.get("expected"),
                    actual=actual,
                    score_detail={
                        "missing_modules": l2["missing_modules"],
                        "missing_doc_chunks": l2["missing_doc_chunks"],
                    },
                )
            except Exception as exc:  # noqa: BLE001
                l2_passed = False
                await _record_case(
                    db, run_id=run_id, case_id=case_id, layer=2,
                    passed=False, expected=case.get("expected"),
                    actual=None, error=f"layer2_exception: {exc}",
                )

    if 3 in case_layers and run_type == "full":
        layer3_total += 1
        if full_err:
            await _record_case(
                db, run_id=run_id, case_id=case_id, layer=3,
                passed=False, expected=case.get("expected"), actual=None, error=full_err,
            )
        else:
            actual = {
                "answer": full_state.get("final") or "",
                "citations": full_state.get("citations") or [],
                "intent": full_state.get("intent"),
                "agent_run_id": full_state.get("agent_run_id"),
            }
            l3 = await asyncio.to_thread(judge_layer3, case, actual)
            if l3.get("scored"):
                detail = l3.get("score_detail") or {}
                overall = float(detail.get("overall") or 0.0)
                layer3_scored += 1
                overall_sum += overall
                for k in rubric_sums:
                    rubric_sums[k] += float(detail.get(k) or 0.0)
                if expected_intent:
                    intent_results.setdefault(expected_intent, []).append(overall)
                await _record_case(
                    db, run_id=run_id, case_id=case_id, layer=3,
                    passed=overall >= 4.0,
                    score=overall,
                    expected=case.get("expected"),
                    actual={
                        "answer_preview": actual["answer"][:300],
                        "answer": actual["answer"],
                        "citations": actual["citations"][:5],
                        "agent_run_id": actual.get("agent_run_id"),
                    },
                    score_detail=detail,
                    judge_reasoning=l3.get("judge_reasoning"),
                    violations=l3.get("violations"),
                )
            else:
                await _record_case(
                    db, run_id=run_id, case_id=case_id, layer=3,
                    passed=False, expected=case.get("expected"),
                    actual={"answer_preview": actual["answer"][:300]},
                    error=l3.get("error"),
                )

    case_passed = layer1_result["passed"] and l2_passed
    if run_type == "full" and 3 in case_layers:
        rows = (
            await db.execute(
                select(EvalCaseResult).where(
                    EvalCaseResult.run_id == run_id,
                    EvalCaseResult.case_id == case_id,
                )
            )
        ).scalars().all()
        case_passed = all(r.passed for r in rows)

    return {
        "layer1": (layer1_total, layer1_pass, layer15_total, layer15_pass),
        "layer2": (layer2_total, layer2_pass),
        "layer3": (layer3_total, layer3_scored),
        "overall_sum": overall_sum,
        "case_passed": case_passed,
    }


async def _apply_gate_flaky_retries(
    db: AsyncSession,
    *,
    run_id: int,
    cases: list[dict[str, Any]],
    case_outcomes: dict[str, bool],
    run_type: str,
) -> dict[str, tuple[int, int]]:
    """Re-run failed gate cases up to 2 extra times; majority vote."""
    overrides: dict[str, tuple[int, int]] = {}
    case_map = {c["id"]: c for c in cases}
    for case_id, passed in list(case_outcomes.items()):
        if passed:
            continue
        case = case_map.get(case_id)
        if not case:
            continue
        pass_count = 1 if case_outcomes.get(case_id) else 0
        attempts = 1
        for _ in range(2):
            attempts += 1
            outcome = await _eval_one_case(
                db,
                run_id=run_id,
                case=case,
                run_type=run_type,
                layer1_total=0,
                layer1_pass=0,
                layer15_total=0,
                layer15_pass=0,
                layer2_total=0,
                layer2_pass=0,
                layer3_total=0,
                layer3_scored=0,
                rubric_sums={"correctness": 0.0, "completeness": 0.0, "citation": 0.0, "compliance": 0.0},
                overall_sum=0.0,
                intent_results={},
                replace_existing=True,
            )
            if outcome["case_passed"]:
                pass_count += 1
        overrides[case_id] = (attempts, pass_count)
        if pass_count >= 2:
            case_outcomes[case_id] = True
    return overrides


async def finalize_gate_run_for_ticket(
    db: AsyncSession,
    *,
    run_id: int,
    ticket_id: int,
    new_case_ids: list[str] | None,
) -> dict[str, Any]:
    """After gate batch completes, update linked ticket status."""
    from src.models import ImprovementTicket

    run = await db.get(EvalRun, run_id)
    ticket = await db.get(ImprovementTicket, ticket_id)
    if not run or not ticket:
        return {"ok": False}
    if ticket.status != "gate_running":
        return {"ok": False, "reason": "ticket not gate_running"}

    from src.services.improvement_tickets import _apply_ticket_status

    ticket.linked_run_id = run_id
    if run.gate_verdict == "pass":
        _apply_ticket_status(ticket, "gate_passed")
        ticket.gate_eval_set_version = get_eval_set_version()
        ticket.gate_pipeline_version = get_pipeline_version()
        ticket.gate_result = f"PASS · Run #{run_id} · L1 {run.layer1_pass}/{run.layer1_total}"
    else:
        _apply_ticket_status(ticket, "gate_failed")
        ticket.gate_result = f"FAIL · Run #{run_id} · verdict={run.gate_verdict}"
    await db.commit()
    return {"ok": True, "verdict": run.gate_verdict, "run_id": run_id}


async def _run_full_flow(db: AsyncSession, case: dict[str, Any]) -> dict[str, Any]:
    import time as _time
    import uuid as _uuid

    from src.agent.graph import build_agent_graph, agent_invoke_config
    from src.agent.harness import (
        FLOW_TIMEOUT_MESSAGE,
        FlowTimeoutError,
        create_harness_context,
        finalize_harness_run,
        invoke_graph_with_flow_timeout,
    )

    role = case.get("role") or "biz_super_admin"
    payroll_access = role == "biz_super_admin"
    app = build_agent_graph()
    session_id = str(_uuid.uuid4())
    flow_started = _time.perf_counter()
    started = _time.perf_counter()
    harness = await create_harness_context(
        db,
        session_id=session_id,
        role=role,
        question=case["query"].strip(),
        actor="eval-runner",
        flow_started_at=flow_started,
    )
    initial: dict[str, Any] = {
        "question": case["query"].strip(),
        "role": role,
        "payroll_access": payroll_access,
        "payroll_confirmed": payroll_access,
        "history": case.get("history") or [],
        "entities": {},
        "plan": [],
        "plan_index": 0,
        "evidence": [],
        "analysis": {},
        "charts": [],
        "citations": [],
        "trace": [],
        "sop_executed": [],
        "replan_count": 0,
        "broaden_search": False,
    }
    flow_timeout = False
    try:
        final_state = await invoke_graph_with_flow_timeout(
            app, initial, agent_invoke_config(db, harness=harness),
        )
    except FlowTimeoutError:
        flow_timeout = True
        final_state = {**initial, "flow_timeout": True, "final": FLOW_TIMEOUT_MESSAGE}
    duration_ms = int((_time.perf_counter() - started) * 1000)
    await finalize_harness_run(harness, final_state, duration_ms=duration_ms, flow_timeout=flow_timeout)
    final_state["agent_run_id"] = str(harness.run_id)
    return final_state


async def _record_case(
    db: AsyncSession,
    *,
    run_id: int,
    case_id: str,
    layer: int,
    passed: bool,
    expected: Any = None,
    actual: Any = None,
    score: float | None = None,
    score_detail: Any = None,
    judge_reasoning: str | None = None,
    violations: list | None = None,
    error: str | None = None,
    attempts: int = 1,
    pass_count: int | None = None,
) -> None:
    row = EvalCaseResult(
        run_id=run_id,
        case_id=case_id,
        layer=layer,
        passed=passed,
        score=score,
        score_detail=score_detail,
        expected=expected,
        actual=actual,
        judge_reasoning=judge_reasoning,
        violations=violations,
        error=error,
        attempts=attempts,
        pass_count=pass_count if pass_count is not None else (1 if passed else 0),
    )
    db.add(row)
    await db.commit()


def _compute_weakness(
    layer1_total: int,
    layer1_pass: int,
    intent_breakdown: dict[str, dict[str, Any]],
    rubric_avg: dict[str, float | None],
    *,
    layer15_total: int = 0,
    layer15_pass: int = 0,
) -> list[dict[str, Any]]:
    weakness: list[dict[str, Any]] = []
    if layer15_total and (layer15_pass / layer15_total) < 0.95:
        weakness.append({
            "kind": "plan_compliance",
            "value": round(layer15_pass / layer15_total, 3),
            "hint": "Planner 计划不变式合规率偏低，检查目录 target_l3 与 analyze/critique 配对",
        })
    if layer1_total and (layer1_pass / layer1_total) < 0.9:
        weakness.append({
            "kind": "intent_accuracy",
            "value": round(layer1_pass / layer1_total, 3),
            "hint": "Planner 意图准确率偏低，重点看 ROUTER 主表判定原则",
        })
    weak_intents = sorted(
        [(intent, data["avg"]) for intent, data in intent_breakdown.items() if data["avg"] < 4.0],
        key=lambda x: x[1],
    )
    for intent, avg in weak_intents[:3]:
        weakness.append({
            "kind": "intent_score_low",
            "intent": intent,
            "avg": avg,
            "hint": f"{intent} 类答案均分 {avg} < 4.0，需要排查 skill/检索",
        })
    weak_rubric = sorted(
        [(k, v) for k, v in rubric_avg.items() if v is not None],
        key=lambda x: x[1],
    )
    if weak_rubric:
        worst_k, worst_v = weak_rubric[0]
        if worst_v < 4.0:
            weakness.append({
                "kind": "rubric_weak",
                "dim": worst_k,
                "avg": round(worst_v, 3),
                "hint": f"{worst_k} 维度均分最低 ({round(worst_v, 3)})，重点改进该维度",
            })
    return weakness
