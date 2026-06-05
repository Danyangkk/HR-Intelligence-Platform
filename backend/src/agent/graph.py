from __future__ import annotations

import time
import uuid
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.analyst import run_analyst
from src.agent.critic import run_critic
from src.agent.harness import (
    FLOW_TIMEOUT_MESSAGE,
    FlowTimeoutError,
    create_harness_context,
    finalize_harness_run,
    invoke_graph_with_flow_timeout,
    with_harness,
)
from src.agent.nodes import compose_answer
from src.agent.planner import run_planner_async
from src.agent.resolver import resolve_entities
from src.agent.skills.runner import begin_agent_run
from src.agent.state import AgentState
from src.agent.supervisor import (
    advance_plan,
    get_current_subtask,
    run_document_from_plan,
    run_retrieve_collect,
    run_retrieve_from_plan,
    run_retrieve_worker,
    supervisor_dispatch,
    supervisor_trace_entry,
)


async def _planner_node(state: AgentState, config) -> dict[str, Any]:
    result = await run_planner_async(state)
    if not result.get("rejected") and not result.get("short_circuit"):
        result["plan_index"] = 0
    return result


async def _supervisor_node(state: AgentState, config) -> dict[str, Any]:
    entry = supervisor_trace_entry(state)
    return {
        "current_subtask": get_current_subtask(state),
        "trace": [entry],
    }


async def _resolver_node(state: AgentState, config) -> dict[str, Any]:
    db: AsyncSession = config["configurable"]["db"]
    result = await resolve_entities(db, state)
    if not result.get("clarify"):
        result["plan_index"] = advance_plan(state)
    return result


async def _retrieve_node(state: AgentState, config) -> dict[str, Any]:
    db: AsyncSession = config["configurable"]["db"]
    return await run_retrieve_from_plan(db, state)


async def _retrieve_worker_node(state: AgentState, config) -> dict[str, Any]:
    return await run_retrieve_worker(state)


async def _retrieve_collect_node(state: AgentState, config) -> dict[str, Any]:
    return await run_retrieve_collect(state)


async def _document_node(state: AgentState, config) -> dict[str, Any]:
    db: AsyncSession = config["configurable"]["db"]
    return await run_document_from_plan(db, state)


async def _analyst_node(state: AgentState, config) -> dict[str, Any]:
    result = run_analyst(state)
    result["plan_index"] = advance_plan(state)
    return result


async def _critic_node(state: AgentState, config) -> dict[str, Any]:
    result = run_critic(state)
    result["plan_index"] = advance_plan(state)
    return result


async def _composer_node(state: AgentState, config) -> dict[str, Any]:
    from src.agent.composer_llm import polish_answer
    from src.agent.composer_rag_llm import rag_answer_draft

    rag_draft = None
    if not state.get("rejected") and any(
        block.get("kind") == "documents" for block in (state.get("evidence") or [])
    ):
        hits: list[dict[str, Any]] = []
        for block in state.get("evidence") or []:
            if block.get("kind") == "documents":
                hits.extend(block.get("hits") or [])
        if hits:
            rag_draft = await rag_answer_draft(state.get("question") or "", hits)

    result = compose_answer(state, rag_draft=rag_draft)
    draft = result.get("final") or ""
    if draft:
        result["final"] = await polish_answer(draft, state)
        ctx_step = "LLM 润色为用户友好表述" if result["final"] != draft else "使用草稿答案（LLM 未启用）"
        trace = list(result.get("trace") or [])
        if trace:
            trace[-1] = {**trace[-1], "summary": trace[-1].get("summary", "") + f" · {ctx_step}"}
            result["trace"] = trace
    return result


async def _replan_node(state: AgentState, config) -> dict[str, Any]:
    count = (state.get("replan_count") or 0) + 1
    ctx = begin_agent_run("Planner", state)
    ctx.run_step("intent-planning", 2, f"证据不足，扩大检索范围（第 {count} 次 replan）")
    return {
        "replan_count": count,
        "broaden_search": True,
        "replan_gaps": list(state.get("replan_gaps") or []),
        "plan_index": 0,
        "evidence": [{"__reset__": True}],
        "analysis": {},
        "charts": [],
        "citations": [{"__reset__": True}],
        "critic_sufficient": False,
        "needs_replan": False,
        "trace": [
            ctx.trace_entry(
                subtask_id="replan",
                summary=f"证据不足，扩大检索范围（第 {count} 次 replan）",
            )
        ],
    }


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("planner", with_harness(_planner_node, name="planner", retryable=True))
    graph.add_node("supervisor", with_harness(_supervisor_node, name="supervisor", retryable=False))
    graph.add_node("resolver", with_harness(_resolver_node, name="resolver", retryable=True))
    graph.add_node("retrieve", with_harness(_retrieve_node, name="retrieve", retryable=True))
    graph.add_node("retrieve_worker", with_harness(_retrieve_worker_node, name="retrieve_worker", retryable=True))
    graph.add_node("retrieve_collect", with_harness(_retrieve_collect_node, name="retrieve_collect", retryable=False))
    graph.add_node("document", with_harness(_document_node, name="document", retryable=True))
    graph.add_node("analyst", with_harness(_analyst_node, name="analyst", retryable=True))
    graph.add_node("critic", with_harness(_critic_node, name="critic", retryable=True))
    graph.add_node("replan", with_harness(_replan_node, name="replan", retryable=False))
    graph.add_node("composer", with_harness(_composer_node, name="composer", retryable=True))

    graph.set_entry_point("planner")
    graph.add_conditional_edges(
        "planner",
        lambda s: "end" if s.get("rejected") or s.get("short_circuit") else "supervisor",
        {"end": END, "supervisor": "supervisor"},
    )
    graph.add_conditional_edges(
        "supervisor",
        supervisor_dispatch,
        [
            END,
            "composer",
            "resolver",
            "retrieve",
            "retrieve_worker",
            "document",
            "analyst",
            "critic",
        ],
    )
    graph.add_edge("resolver", "supervisor")
    graph.add_edge("retrieve", "supervisor")
    graph.add_edge("retrieve_worker", "retrieve_collect")
    graph.add_edge("retrieve_collect", "supervisor")
    graph.add_edge("document", "supervisor")
    graph.add_edge("analyst", "critic")
    graph.add_conditional_edges(
        "critic",
        lambda s: "replan" if s.get("needs_replan") else "supervisor",
        {"replan": "replan", "supervisor": "supervisor"},
    )
    graph.add_edge("replan", "planner")
    graph.add_edge("composer", END)
    return graph.compile()


DEFAULT_RECURSION_LIMIT = 50


def agent_invoke_config(
    db: AsyncSession,
    *,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    harness=None,
) -> dict[str, Any]:
    """LangGraph invoke config; attribution+replan fan-out can exceed default limit of 25."""
    configurable: dict[str, Any] = {"db": db}
    if harness is not None:
        configurable["harness"] = harness
    return {"configurable": configurable, "recursion_limit": recursion_limit}


async def run_agent(
    db: AsyncSession,
    *,
    question: str,
    role: str = "staff",
    history: list[dict[str, Any]] | None = None,
    session_id: str | None = None,
    entities: dict[str, Any] | None = None,
    actor: str | None = None,
    payroll_access: bool = False,
    payroll_confirmed: bool = False,
) -> dict[str, Any]:
    app = build_agent_graph()
    session_id = session_id or str(uuid.uuid4())
    started = time.perf_counter()
    flow_started = time.perf_counter()
    harness = await create_harness_context(
        db,
        session_id=session_id,
        role=role,
        question=question.strip(),
        actor=actor,
        flow_started_at=flow_started,
    )
    initial: AgentState = {
        "question": question.strip(),
        "role": role,
        "payroll_access": payroll_access,
        "payroll_confirmed": payroll_confirmed,
        "history": history or [],
        "entities": dict(entities or {}),
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
            app,
            initial,
            agent_invoke_config(db, harness=harness),
        )
    except FlowTimeoutError:
        flow_timeout = True
        final_state = {**initial, "flow_timeout": True, "final": FLOW_TIMEOUT_MESSAGE}
    duration_ms = int((time.perf_counter() - started) * 1000)
    await finalize_harness_run(harness, final_state, duration_ms=duration_ms, flow_timeout=flow_timeout)
    return {
        "session_id": session_id,
        "run_id": str(harness.run_id),
        "duration_ms": duration_ms,
        "question": question,
        "role": role,
        "intent": final_state.get("intent"),
        "rejected": bool(final_state.get("rejected")),
        "reject_reason": final_state.get("reject_reason"),
        "clarify": final_state.get("clarify"),
        "plan": final_state.get("plan") or [],
        "trace": final_state.get("trace") or [],
        "answer": final_state.get("final") or "",
        "citations": final_state.get("citations") or [],
        "charts": final_state.get("charts") or [],
        "analysis": final_state.get("analysis") or {},
        "replan_count": final_state.get("replan_count") or 0,
        "limitation": final_state.get("limitation") or "",
        "entities": final_state.get("entities") or {},
        "evidence_count": len(final_state.get("evidence") or []),
        "flow_timeout": flow_timeout,
    }
