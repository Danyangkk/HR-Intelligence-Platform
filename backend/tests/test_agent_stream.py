from __future__ import annotations

import json

import pytest

from src.agent.stream import format_sse, run_agent_stream
from src.db.session import AsyncSessionLocal


def _parse_sse_events(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data_line = ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_line = line.split(":", 1)[1].strip()
        if data_line:
            events.append((event_name, json.loads(data_line)))
    return events


async def _collect_stream(
    question: str,
    *,
    role: str = "viewer",
    payroll_confirmed: bool = False,
) -> list[tuple[str, dict]]:
    chunks: list[str] = []
    async with AsyncSessionLocal() as db:
        async for chunk in run_agent_stream(
            db,
            question=question,
            role=role,
            payroll_confirmed=payroll_confirmed,
        ):
            chunks.append(chunk)
    return _parse_sse_events("".join(chunks))


@pytest.mark.asyncio
async def test_agent_stream_compare_emits_plan_and_answer():
    events = await _collect_stream(
        "对比各事业部人均成本谁高",
        role="biz_super_admin",
        payroll_confirmed=True,
    )
    names = [name for name, _ in events]
    assert "plan" in names
    assert "node_start" in names
    assert "answer" in names
    assert names[-1] == "done"
    plan = next(data for name, data in events if name == "plan")
    assert plan["intent"] == "compare"
    assert "人均成本" in plan.get("orch_sub", "") or "对比" in plan.get("orch_sub", "")
    assert len(plan["subtasks"]) >= 3
    answer = next(data for name, data in events if name == "answer")
    assert answer["text"]
    assert any(name == "chart" for name, _ in events)


@pytest.mark.asyncio
async def test_agent_stream_reject_salary():
    events = await _collect_stream("张三的工资条是多少")
    names = [name for name, _data in events]
    assert "reject" in names
    reject = next(data for name, data in events if name == "reject")
    assert "薪资" in reject["reason"]


def test_format_sse():
    raw = format_sse("plan", {"intent": "lookup"})
    assert raw.startswith("event: plan\n")
    assert '"lookup"' in raw
