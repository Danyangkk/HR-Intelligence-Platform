from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.graph import agent_invoke_config, build_agent_graph
from src.agent.harness import (
    FLOW_TIMEOUT_MESSAGE,
    FlowTimeoutError,
    create_harness_context,
    finalize_harness_run,
    iter_graph_with_flow_timeout,
)
from src.agent.planner import build_orch_summary
from src.agent.state import AgentState
from src.services.agent_runs import infer_tools_used, persist_agent_run
from src.services.audit import write_audit

_NODE_AGENT: dict[str, str] = {
    "planner": "Planner",
    "supervisor": "Supervisor",
    "resolver": "Resolver",
    "retrieve": "Retriever",
    "retrieve_worker": "Retriever",
    "retrieve_collect": "Supervisor",
    "document": "Retriever",
    "analyst": "Analyst",
    "critic": "Critic",
    "replan": "Planner",
    "composer": "Composer",
}

_NODE_DEFAULT_SKILL: dict[str, str | None] = {
    "planner": None,
    "supervisor": None,
    "resolver": "实体解析",
    "retrieve": "结构化取数",
    "retrieve_worker": "结构化取数",
    "retrieve_collect": None,
    "document": "文档检索与解读",
    "analyst": "对比与基准",
    "critic": "证据校验",
    "replan": None,
    "composer": "答案组织与引用",
}


def format_sse(event: str, data: dict[str, Any], *, run_id: str | None = None) -> str:
    payload = {**data}
    if run_id:
        payload.setdefault("run_id", run_id)
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _last_trace(update: dict[str, Any]) -> dict[str, Any] | None:
    trace = update.get("trace") or []
    return trace[-1] if trace else None


def _merge_state(state: AgentState, update: dict[str, Any]) -> AgentState:
    merged: AgentState = dict(state)
    for key, value in update.items():
        if key == "trace" and isinstance(value, list):
            merged["trace"] = value
        else:
            merged[key] = value  # type: ignore[literal-required]
    return merged


def _plan_subtasks(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "type": item.get("type"),
            "goal": item.get("goal"),
            "agent": item.get("assigned_agent"),
            "target_l3": item.get("target_l3"),
            "retrieve_mode": item.get("retrieve_mode"),
        }
        for item in plan
    ]


def _node_meta(node_name: str, update: dict[str, Any]) -> tuple[str, str | None, str]:
    trace_entry = _last_trace(update) or {}
    agent = trace_entry.get("agent") or _NODE_AGENT.get(node_name, node_name)
    skill = trace_entry.get("skill") or _NODE_DEFAULT_SKILL.get(node_name)
    subtask_id = trace_entry.get("subtask_id") or node_name
    return agent, skill, subtask_id


def _node_start_label(node_name: str, state: AgentState) -> str:
    question = (state.get("question") or "").strip()
    preview = question if len(question) <= 36 else question[:36] + "…"
    intent = state.get("intent")
    if node_name == "planner":
        return f"分析问题并规划：{preview}"
    if node_name == "supervisor":
        sub = state.get("current_subtask") or {}
        goal = str(sub.get("goal") or preview)[:40]
        agent = sub.get("assigned_agent") or "Agent"
        return f"Supervisor 派发 {sub.get('type', 'subtask')} → {agent}：{goal}"
    if node_name == "document":
        return f"知识库检索(RAG)：检索现行制度 · {preview}"
    if node_name == "retrieve" and intent == "lookup":
        employee = (state.get("entities") or {}).get("employee") or {}
        who = employee.get("姓名") or "目标员工"
        return f"结构化取数：查询 {who} 的业务表记录"
    if node_name == "retrieve" and intent == "compare":
        org = (state.get("entities") or {}).get("org") or {}
        scope = org.get("事业部") or "全部事业部"
        return f"结构化取数：拉取 {scope} 成本与编制"
    if node_name == "retrieve" and intent == "attribution":
        topic = (state.get("entities") or {}).get("topic") or "综合"
        return f"结构化取数：多表支撑「{topic}」归因"
    if node_name == "retrieve":
        return "结构化取数（按意图匹配业务表）"
    labels = {
        "resolver": f"实体解析（仅结构化查询需要）：{preview}",
        "analyst": "数据分析：对比/归因并引用指标口径",
        "critic": "证据校验：是否充分、可否作答",
        "replan": "证据不足，扩大检索后重新规划",
        "composer": "组织答案、图表与引用",
    }
    return labels.get(node_name, f"执行节点 {node_name}")


def _normalize_title_path(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_locator(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int | str]] = set()
    for item in citations:
        if item.get("kind") == "doc":
            doc_id = item.get("doc_id")
            seq = item.get("seq")
            key = (str(item.get("l3_id")), str(doc_id), seq if seq is not None else "")
            if key in seen:
                continue
            seen.add(key)
            title_path = _normalize_title_path(item.get("title_path"))
            normalized.append(
                {
                    "kind": "doc",
                    "l3_id": item.get("l3_id"),
                    "doc_id": doc_id,
                    "seq": seq,
                    "title_path": title_path,
                    "chunk": item.get("chunk") or "",
                    "score": item.get("score"),
                }
            )
        else:
            normalized.append(
                {
                    "kind": "data",
                    "l3_id": item.get("l3_id"),
                    "locator": _normalize_locator(item.get("locator")),
                }
            )
    return normalized


def _planner_direct_reply(update: dict[str, Any]) -> tuple[str, str] | None:
    """Planner short-circuit: chitchat / unmatched friendly reply without orchestration."""
    final = str(update.get("final") or "").strip()
    if not final:
        return None
    if update.get("short_circuit") or (
        update.get("intent") == "chitchat" and not (update.get("plan") or [])
    ):
        return ("chitchat", final)
    if update.get("unmatched"):
        return ("unmatched", final)
    return None


def _emit_node_events(
    node_name: str,
    update: dict[str, Any],
    state: AgentState,
    *,
    run_id: str,
) -> list[str]:
    agent, skill, subtask_id = _node_meta(node_name, update)
    trace_entry = _last_trace(update) or {}
    summary = trace_entry.get("summary") or ""
    start_label = _node_start_label(node_name, state)
    events = [
        format_sse(
            "node_start",
            {
                "node": node_name,
                "subtask_id": subtask_id,
                "agent": agent,
                "skill": skill,
                "label": start_label,
            },
            run_id=run_id,
        ),
        format_sse(
            "node_done",
            {
                "node": node_name,
                "subtask_id": subtask_id,
                "agent": agent,
                "skill": skill,
                "summary": summary or start_label,
            },
            run_id=run_id,
        ),
    ]
    return events


def _result_from_state(
    state: AgentState,
    *,
    question: str,
    role: str,
    session_id: str,
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "duration_ms": duration_ms,
        "question": question,
        "role": role,
        "intent": state.get("intent"),
        "rejected": bool(state.get("rejected")),
        "reject_reason": state.get("reject_reason"),
        "clarify": state.get("clarify"),
        "plan": state.get("plan") or [],
        "trace": state.get("trace") or [],
        "answer": state.get("final") or "",
        "citations": state.get("citations") or [],
        "charts": state.get("charts") or [],
        "analysis": state.get("analysis") or {},
        "replan_count": state.get("replan_count") or 0,
        "limitation": state.get("limitation") or "",
        "entities": state.get("entities") or {},
        "evidence_count": len(state.get("evidence") or []),
    }


async def _persist_observability(
    db: AsyncSession,
    *,
    actor: str | None,
    role: str,
    question: str,
    state: AgentState,
    session_id: str,
    duration_ms: int,
) -> None:
    result = _result_from_state(
        state,
        question=question,
        role=role,
        session_id=session_id,
        duration_ms=duration_ms,
    )
    await persist_agent_run(
        db,
        session_id=session_id,
        actor=actor,
        role=role,
        question=question,
        result=result,
        duration_ms=duration_ms,
    )
    await write_audit(
        db,
        actor=actor,
        action="agent.ask",
        target_id=session_id,
        detail={
            "question": question,
            "intent": result.get("intent"),
            "role": role,
            "rejected": result.get("rejected"),
            "replan_count": result.get("replan_count"),
            "duration_ms": duration_ms,
            "tools_used": infer_tools_used(state.get("intent"), state.get("trace") or []),
        },
    )


async def run_agent_stream(
    db: AsyncSession,
    *,
    question: str,
    role: str = "viewer",
    history: list[dict[str, Any]] | None = None,
    session_id: str | None = None,
    actor: str | None = None,
    entities: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    app = build_agent_graph()
    q = question.strip()
    session_id = session_id or str(uuid.uuid4())
    started = time.perf_counter()
    flow_started = time.perf_counter()
    harness = await create_harness_context(
        db,
        session_id=session_id,
        role=role,
        question=q,
        actor=actor,
        flow_started_at=flow_started,
    )
    initial: AgentState = {
        "question": q,
        "role": role,
        "history": history or [],
        "entities": dict(entities or {}),
        "plan": [],
        "evidence": [],
        "analysis": {},
        "charts": [],
        "citations": [],
        "trace": [],
        "replan_count": 0,
        "broaden_search": False,
    }
    state: AgentState = dict(initial)
    config = agent_invoke_config(db, harness=harness)
    flow_timeout = False
    run_id = str(harness.run_id)

    try:
        async for node_name, update in iter_graph_with_flow_timeout(app, initial, config):
            state = _merge_state(state, update)

            if node_name == "planner":
                direct = _planner_direct_reply(update)
                if direct:
                    kind, text = direct
                    yield format_sse(
                        "answer",
                        {
                            "text": text,
                            "citations": [],
                            "limitation": "",
                            "intent": update.get("intent") or ("chitchat" if kind == "chitchat" else ""),
                            "entities": state.get("entities") or {},
                            "session_id": session_id,
                            "direct": True,
                        },
                        run_id=run_id,
                    )
                    yield format_sse("done", {}, run_id=run_id)
                    return
                if update.get("rejected"):
                    if update.get("unmatched"):
                        yield format_sse(
                            "answer",
                            {
                                "text": update.get("final") or "抱歉哦～ 我没有查到问题的相关答案，可以换个问题试试看呢。",
                                "citations": [],
                                "limitation": "",
                                "intent": "",
                                "entities": state.get("entities") or {},
                                "session_id": session_id,
                                "direct": True,
                            },
                            run_id=run_id,
                        )
                    else:
                        yield format_sse(
                            "reject",
                            {"reason": update.get("reject_reason") or "无法回答。"},
                            run_id=run_id,
                        )
                    yield format_sse("done", {}, run_id=run_id)
                    return
                intent = update.get("intent") or "lookup"
                plan = update.get("plan") or []
                yield format_sse(
                    "plan",
                    {
                        "intent": intent,
                        "question": q,
                        "orch_sub": build_orch_summary(intent, q),
                        "retrieve_mode": "rag" if intent == "policy" else "structured",
                        "subtasks": _plan_subtasks(plan),
                        "session_id": session_id,
                    },
                    run_id=run_id,
                )

            if node_name == "resolver" and update.get("clarify"):
                clarify = update["clarify"]
                for event in _emit_node_events(node_name, update, state, run_id=run_id):
                    yield event
                yield format_sse(
                    "clarify",
                    {
                        "question": clarify.get("question") or "需要补充信息。",
                        "options": clarify.get("options") or [],
                        "kind": clarify.get("kind") or "employee",
                        "intent": state.get("intent"),
                        "entities": state.get("entities") or {},
                        "session_id": session_id,
                    },
                    run_id=run_id,
                )
                yield format_sse("done", {}, run_id=run_id)
                return

            for event in _emit_node_events(node_name, update, state, run_id=run_id):
                yield event

            if node_name == "analyst":
                for chart in update.get("charts") or []:
                    yield format_sse("chart", {"chart_spec": chart}, run_id=run_id)

            if node_name == "composer":
                yield format_sse(
                    "answer",
                    {
                        "text": state.get("final") or "",
                        "citations": _normalize_citations(state.get("citations") or []),
                        "limitation": state.get("limitation") or "",
                        "intent": state.get("intent"),
                        "entities": state.get("entities") or {},
                        "session_id": session_id,
                    },
                    run_id=run_id,
                )
                yield format_sse("done", {}, run_id=run_id)
                return

        yield format_sse("done", {}, run_id=run_id)
    except FlowTimeoutError:
        flow_timeout = True
        state = {**state, "flow_timeout": True, "final": FLOW_TIMEOUT_MESSAGE}
        yield format_sse(
            "answer",
            {
                "text": FLOW_TIMEOUT_MESSAGE,
                "citations": [],
                "limitation": "",
                "intent": state.get("intent") or "",
                "entities": state.get("entities") or {},
                "session_id": session_id,
                "direct": True,
            },
            run_id=run_id,
        )
        yield format_sse("done", {}, run_id=run_id)
    except Exception as exc:
        from langgraph.errors import GraphRecursionError

        if isinstance(exc, GraphRecursionError):
            yield format_sse(
                "answer",
                {
                    "text": "这个问题分析步骤较多，系统处理超时了。请尝试缩小范围（如指定部门/时间）后重试。",
                    "citations": [],
                    "limitation": "",
                    "intent": state.get("intent") or "",
                    "entities": state.get("entities") or {},
                    "session_id": session_id,
                    "direct": True,
                },
                run_id=run_id,
            )
            yield format_sse("done", {}, run_id=run_id)
        else:
            raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        await finalize_harness_run(
            harness,
            state,
            duration_ms=duration_ms,
            flow_timeout=flow_timeout,
        )
        await _persist_observability(
            db,
            actor=actor,
            role=role,
            question=q,
            state=state,
            session_id=session_id,
            duration_ms=duration_ms,
        )
