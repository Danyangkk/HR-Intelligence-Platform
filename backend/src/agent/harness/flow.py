from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from typing import Any

from src.agent.harness.constants import FLOW_TIMEOUT_S
from src.agent.harness.context import flow_elapsed_s, get_harness
from src.agent.harness.exceptions import FlowTimeoutError


async def invoke_graph_with_flow_timeout(app, initial: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    harness = get_harness(config)
    remaining = max(FLOW_TIMEOUT_S - flow_elapsed_s(harness), 0.01) if harness else FLOW_TIMEOUT_S
    try:
        return await asyncio.wait_for(app.ainvoke(initial, config=config), timeout=remaining)
    except asyncio.TimeoutError as exc:
        raise FlowTimeoutError() from exc


async def iter_graph_with_flow_timeout(
    app,
    initial: dict[str, Any],
    config: dict[str, Any],
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    harness = get_harness(config)
    deadline = (harness.flow_started_at + FLOW_TIMEOUT_S) if harness else (time.perf_counter() + FLOW_TIMEOUT_S)

    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def producer() -> None:
        try:
            async for chunk in app.astream(initial, config=config, stream_mode="updates"):
                await queue.put(("chunk", chunk))
        except Exception as exc:
            await queue.put(("error", exc))
        finally:
            await queue.put(("done", None))

    task = asyncio.create_task(producer())
    try:
        while True:
            remaining = max(deadline - time.perf_counter(), 0.0)
            if remaining <= 0:
                task.cancel()
                raise FlowTimeoutError()

            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                task.cancel()
                raise FlowTimeoutError() from exc

            if kind == "done":
                break
            if kind == "error":
                raise payload
            for node_name, update in payload.items():
                yield node_name, update
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
