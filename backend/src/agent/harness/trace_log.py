from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.agent.harness.context import HarnessContext
from src.agent.harness.decision import extract_decision, extract_skills, extract_tools
from src.agent.harness.file_log import log_node
from src.models import AgentNodeTrace
from src.services.harness_trace import persist_node_trace_row

logger = logging.getLogger("agent.harness")

_NODE_AGENT: dict[str, str] = {
    "planner": "Planner",
    "supervisor": "Supervisor",
    "resolver": "Resolver",
    "retrieve": "Retriever",
    "retrieve_worker": "Retriever",
    "retrieve_collect": "Retriever",
    "document": "Retriever",
    "analyst": "Analyst",
    "critic": "Critic",
    "replan": "Planner",
    "composer": "Composer",
}

_TRACE_NODE: dict[str, str] = {
    "planner": "planner",
    "supervisor": "supervisor",
    "resolver": "resolver",
    "retrieve": "retriever",
    "retrieve_worker": "retriever",
    "retrieve_collect": "retriever",
    "document": "document",
    "analyst": "analyst",
    "critic": "critic",
    "replan": "planner",
    "composer": "composer",
}


def trace_node_name(node_name: str) -> str:
    return _TRACE_NODE.get(node_name, node_name)


def trace_agent_name(node_name: str, result: dict[str, Any]) -> str:
    trace_entry = (result.get("trace") or [None])[-1] or {}
    return str(trace_entry.get("agent") or _NODE_AGENT.get(node_name, node_name))


def log_harness_event(
    *,
    level: str,
    harness: HarnessContext | None,
    node: str,
    agent: str,
    status: str,
    attempt: int,
    duration_ms: int,
    intent: str | None = None,
    error_type: str | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
) -> None:
    payload = {
        "level": level,
        "ts": time.time(),
        "run_id": str(run_id or (harness.run_id if harness else "")),
        "session_id": session_id or (harness.session_id if harness else ""),
        "node": node,
        "agent": agent,
        "status": status,
        "attempt": attempt,
        "duration_ms": duration_ms,
        "intent": intent or "",
        "error_type": error_type or "",
    }
    line = json.dumps(payload, ensure_ascii=False)
    if level == "ERROR":
        logger.error(line)
    else:
        logger.info(line)


async def record_node_trace(
    harness: HarnessContext | None,
    *,
    node_name: str,
    result: dict[str, Any] | None,
    state: dict[str, Any],
    status: str,
    attempt: int,
    duration_ms: int,
    error_type: str | None = None,
) -> None:
    if not harness:
        return

    harness.node_seq += 1
    harness.node_count += 1
    trace_node = trace_node_name(node_name)
    agent = trace_agent_name(node_name, result or {})
    decision = extract_decision(node_name, result or {}, state)  # type: ignore[arg-type]
    skills = extract_skills(result or {}, state)  # type: ignore[arg-type]
    tools = extract_tools(result or {})

    row = AgentNodeTrace(
        run_id=harness.run_id,
        seq=harness.node_seq,
        node=trace_node,
        agent=agent,
        skills_loaded=skills,
        tools_called=tools,
        status=status,
        attempt=attempt,
        duration_ms=duration_ms,
        decision=decision,
        error_type=error_type,
    )
    await persist_node_trace_row(harness.db, row)

    log_node(
        run_id=str(harness.run_id),
        seq=harness.node_seq,
        node=trace_node,
        agent=agent,
        status=status,
        attempt=attempt,
        duration_ms=duration_ms,
        intent=str(state.get("intent") or (result.get("intent") if result else "") or ""),
        decision=decision if isinstance(decision, dict) else None,
        error_type=error_type,
    )

    log_harness_event(
        level="ERROR" if status in {"failed", "timeout"} and error_type else "INFO",
        harness=harness,
        node=trace_node,
        agent=agent,
        status=status,
        attempt=attempt,
        duration_ms=duration_ms,
        intent=str(state.get("intent") or result.get("intent") if result else ""),
        error_type=error_type,
    )

    harness.traces.append(
        {
            "seq": harness.node_seq,
            "node": trace_node,
            "status": status,
            "attempt": attempt,
            "duration_ms": duration_ms,
            "decision": decision,
        }
    )

    if isinstance(decision, dict):
        if trace_node == "document" and decision.get("chunks_hit") == 0:
            harness.badcase_signals.append("rag_zero_hit")
        if trace_node == "critic" and decision.get("decision") == "pass_with_limit":
            replan = int(state.get("replan_count") or 0)
            if replan >= 2:
                harness.badcase_signals.append("replan_exhausted")
