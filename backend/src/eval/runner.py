"""Eval 跑批 orchestrator — 一键跑完 30 条 mock 评测集。

流程：
  1. 加载 eval_set.yaml
  2. 创建 eval_run row (status=running)
  3. 对每条 case：
     - 跑 Planner → layer1 判定
     - 若需要 layer2/3：跑全流程 run_agent → 抽 evidence + answer
     - layer2：集合比对 modules / doc_chunks
     - layer3：LLM-as-judge 打分（单条失败不阻塞整批）
     - 每条 case 的每个 layer 落一行 eval_case_result
  4. 汇总三层指标 → 更新 eval_run（layer3 均分 / 各维度均分 / 按意图分布 / 弱项清单）
"""
from __future__ import annotations

import asyncio
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.graph import run_agent
from src.eval.layer1 import judge_layer1, run_planner_for_case
from src.eval.layer2 import collect_actual_retrieval, judge_layer2
from src.eval.layer3 import judge_layer3
from src.eval.loader import get_case_intent, load_eval_set
from src.models import EvalCaseResult, EvalRun


async def create_eval_run(
    db: AsyncSession,
    *,
    version: str = "dev",
    trigger: str = "manual",
    triggered_by: str | None = None,
    case_limit: int | None = None,
) -> int:
    """预创建 eval_run（status=running），供 API 立即返回 run_id 后后台跑批。"""
    cases = load_eval_set()
    if case_limit:
        cases = cases[:case_limit]
    run = EvalRun(
        version=version,
        trigger=trigger,
        triggered_by=triggered_by,
        status="running",
        total_cases=len(cases),
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
    case_limit: int | None = None,
) -> int:
    """跑一次评测集，返回 eval_run.id。

    run_id：若已预创建则续跑并更新该条记录；否则新建。
    only_layer1=True：仅跑 Planner 层（最快，不调全流程，不调 LLM-as-judge）。
    case_limit：测试用，仅跑前 N 条。
    """
    cases = load_eval_set()
    if case_limit:
        cases = cases[:case_limit]

    if run_id:
        run = await db.get(EvalRun, run_id)
        if not run:
            raise ValueError(f"eval run {run_id} not found")
        run.status = "running"
        run.total_cases = len(cases)
        await db.commit()
    else:
        run = EvalRun(
            version=version,
            trigger=trigger,
            triggered_by=triggered_by,
            status="running",
            total_cases=len(cases),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

    started = time.perf_counter()
    layer1_total = layer1_pass = 0
    layer2_total = layer2_pass = 0
    layer3_total = layer3_scored = 0
    rubric_sums = {"correctness": 0.0, "completeness": 0.0, "citation": 0.0, "compliance": 0.0}
    overall_sum = 0.0
    intent_results: dict[str, list[float]] = {}

    for case in cases:
        case_id = case["id"]
        expected_intent = get_case_intent(case)
        case_layers = set(case.get("layer") or [1])
        if only_layer1:
            case_layers = {1}

        # ----- Layer 1：跑 Planner -----
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
            run_id=run.id,
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

        # ----- 是否需要跑全流程 -----
        need_full = bool(case_layers & {2, 3})
        if not need_full:
            continue

        # 安全 reject 类 case：planner 已 reject，不再跑全流程（也跑不了）
        if planner_state.get("rejected") and not case.get("expected", {}).get("intent"):
            continue

        full_state: dict[str, Any] = {}
        full_err: str | None = None
        try:
            full_state = await _run_full_flow(db, case)
        except Exception as exc:  # noqa: BLE001
            full_err = f"agent_run_failed: {exc}"

        # ----- Layer 2：检索质量 -----
        if 2 in case_layers:
            layer2_total += 1
            if full_err:
                await _record_case(
                    db, run_id=run.id, case_id=case_id, layer=2,
                    passed=False, expected=case.get("expected"), actual=None,
                    error=full_err,
                )
            else:
                try:
                    actual_retrieval = await collect_actual_retrieval(db, full_state)
                    l2 = judge_layer2(case, actual_retrieval)
                    if l2["passed"]:
                        layer2_pass += 1
                    await _record_case(
                        db, run_id=run.id, case_id=case_id, layer=2,
                        passed=l2["passed"],
                        expected=case.get("expected"),
                        actual=l2["actual"],
                        score_detail={
                            "missing_modules": l2["missing_modules"],
                            "missing_doc_chunks": l2["missing_doc_chunks"],
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    await _record_case(
                        db, run_id=run.id, case_id=case_id, layer=2,
                        passed=False, expected=case.get("expected"),
                        actual=None, error=f"layer2_exception: {exc}",
                    )

        # ----- Layer 3：LLM-as-judge -----
        if 3 in case_layers:
            layer3_total += 1
            if full_err:
                await _record_case(
                    db, run_id=run.id, case_id=case_id, layer=3,
                    passed=False, expected=case.get("expected"), actual=None,
                    error=full_err,
                )
                continue
            actual = {
                "answer": full_state.get("final") or "",
                "citations": full_state.get("citations") or [],
                "intent": full_state.get("intent"),
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
                    db, run_id=run.id, case_id=case_id, layer=3,
                    passed=overall >= 4.0,  # ≥4 视为 pass（趋势监控，非门禁）
                    score=overall,
                    expected=case.get("expected"),
                    actual={"answer_preview": actual["answer"][:300], "citations": actual["citations"][:5]},
                    score_detail=detail,
                    judge_reasoning=l3.get("judge_reasoning"),
                    violations=l3.get("violations"),
                )
            else:
                await _record_case(
                    db, run_id=run.id, case_id=case_id, layer=3,
                    passed=False, expected=case.get("expected"),
                    actual={"answer_preview": actual["answer"][:300]},
                    error=l3.get("error"),
                )

    # ----- 汇总 -----
    duration_ms = int((time.perf_counter() - started) * 1000)
    layer3_avg = overall_sum / layer3_scored if layer3_scored else None
    rubric_avg = {k: (v / layer3_scored if layer3_scored else None) for k, v in rubric_sums.items()}
    intent_breakdown = {
        intent: {
            "count": len(scores),
            "avg": round(sum(scores) / len(scores), 3),
        }
        for intent, scores in intent_results.items()
    }
    weakness = _compute_weakness(layer1_total, layer1_pass, intent_breakdown, rubric_avg)

    # 重新 fetch 一遍避免 stale state
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
    await db.commit()
    return run.id


async def _run_full_flow(db: AsyncSession, case: dict[str, Any]) -> dict[str, Any]:
    """跑全流程，返回 final_state（含 evidence/citations/final/intent）。

    直接走底层 graph.invoke 而不是 run_agent，因为 run_agent 返回值只有 evidence_count
    没有完整 evidence；layer2 需要 evidence 比对模块命中，所以这里走底层 state。

    现场重跑机制（规格 §4）：每条 case 现场喂给当前系统跑一遍，不读历史 trace。
    """
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
    payroll_access = (role == "biz_super_admin")
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
    )
    db.add(row)
    await db.commit()


def _compute_weakness(
    layer1_total: int,
    layer1_pass: int,
    intent_breakdown: dict[str, dict[str, Any]],
    rubric_avg: dict[str, float | None],
) -> list[dict[str, Any]]:
    weakness: list[dict[str, Any]] = []
    # 意图弱项：< 4.0 / 准确率低
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
