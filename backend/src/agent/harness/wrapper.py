from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any, Callable

from src.agent.harness.constants import FLOW_TIMEOUT_MESSAGE, FLOW_TIMEOUT_S, MAX_RETRY, NODE_TIMEOUT_S, RETRY_BACKOFF_S
from src.agent.harness.context import flow_timed_out, get_harness
from src.agent.harness.exceptions import FlowTimeoutError
from src.agent.harness.trace_log import record_node_trace, trace_agent_name
from src.agent.state import AgentState
from src.agent.supervisor import advance_plan, get_current_subtask


def is_business_terminal(result: dict[str, Any]) -> bool:
    if result.get("short_circuit"):
        return True
    if result.get("clarify"):
        return True
    if result.get("rejected"):
        return True
    if result.get("pii_denied"):
        return True
    if result.get("validation_error"):
        return True
    return False


def is_non_retryable_exception(exc: BaseException) -> bool:
    return isinstance(exc, (FlowTimeoutError, ValueError, TypeError))


def node_failure_fallback(node_name: str, state: AgentState, *, error_type: str) -> dict[str, Any]:
    subtask = get_current_subtask(state) or {}
    subtask_id = subtask.get("id") or node_name
    trace = [
        {
            "subtask_id": subtask_id,
            "agent": trace_agent_name(node_name, {}),
            "summary": f"{node_name} 节点失败({error_type})",
        }
    ]

    if node_name in {"retrieve", "retrieve_worker", "document"}:
        patch: dict[str, Any] = {"trace": trace, "harness_node_failed": node_name}
        if node_name == "retrieve":
            patch["plan_index"] = advance_plan(state)
        return patch

    if node_name == "critic":
        return {
            "trace": trace,
            "critic_sufficient": True,
            "needs_replan": False,
            "limitation": "质检节点异常，基于现有证据作答",
            "plan_index": advance_plan(state),
        }

    if node_name == "composer":
        return {"trace": trace, "final": "系统繁忙，请稍后重试"}

    if node_name == "planner":
        return {"trace": trace, "rejected": True, "reject_reason": "规划节点异常，请稍后重试", "final": "系统繁忙，请稍后重试"}

    return {"trace": trace, "harness_error": error_type}


def flow_timeout_patch(state: AgentState) -> dict[str, Any]:
    return {
        "flow_timeout": True,
        "final": FLOW_TIMEOUT_MESSAGE,
        "rejected": False,
        "trace": [
            {
                "subtask_id": "flow",
                "agent": "Harness",
                "summary": "全流程超时",
            }
        ],
    }


def with_harness(
    node_fn: Callable[..., Any],
    *,
    name: str,
    timeout: float = NODE_TIMEOUT_S,
    max_retry: int = MAX_RETRY,
    retryable: bool = True,
):
    async def wrapped(state: AgentState, config) -> dict[str, Any]:
        harness = get_harness(config)
        if harness and flow_timed_out(harness):
            patch = flow_timeout_patch(state)
            await record_node_trace(
                harness,
                node_name=name,
                result=patch,
                state=state,
                status="timeout",
                attempt=1,
                duration_ms=0,
                error_type="flow_timeout",
            )
            raise FlowTimeoutError()

        attempt = 0
        max_attempts = max_retry + 1
        last_error_type: str | None = None

        while attempt < max_attempts:
            attempt += 1
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(node_fn(state, config), timeout=timeout)
                duration_ms = int((time.perf_counter() - started) * 1000)

                if is_business_terminal(result):
                    await record_node_trace(
                        harness,
                        node_name=name,
                        result=result,
                        state=state,
                        status="ok",
                        attempt=attempt,
                        duration_ms=duration_ms,
                    )
                    return result

                await record_node_trace(
                    harness,
                    node_name=name,
                    result=result,
                    state=state,
                    status="ok",
                    attempt=attempt,
                    duration_ms=duration_ms,
                )
                return result
            except asyncio.TimeoutError:
                duration_ms = int((time.perf_counter() - started) * 1000)
                last_error_type = "timeout"
                will_retry = retryable and attempt < max_attempts
                await record_node_trace(
                    harness,
                    node_name=name,
                    result=None,
                    state=state,
                    status="retry" if will_retry else "timeout",
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error_type=last_error_type,
                )
                if will_retry:
                    await asyncio.sleep(RETRY_BACKOFF_S[min(attempt - 1, len(RETRY_BACKOFF_S) - 1)])
                    continue
                return node_failure_fallback(name, state, error_type=last_error_type)
            except FlowTimeoutError:
                raise
            except Exception as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                last_error_type = type(exc).__name__
                non_retryable = is_non_retryable_exception(exc) or not retryable
                will_retry = retryable and not non_retryable and attempt < max_attempts
                await record_node_trace(
                    harness,
                    node_name=name,
                    result=None,
                    state=state,
                    status="retry" if will_retry else "failed",
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error_type=last_error_type,
                )
                if will_retry:
                    await asyncio.sleep(RETRY_BACKOFF_S[min(attempt - 1, len(RETRY_BACKOFF_S) - 1)])
                    continue
                return node_failure_fallback(name, state, error_type=last_error_type or "error")

        return node_failure_fallback(name, state, error_type=last_error_type or "error")

    wrapped.__name__ = getattr(node_fn, "__name__", name)
    wrapped.__qualname__ = getattr(node_fn, "__qualname__", name)
    return wrapped
