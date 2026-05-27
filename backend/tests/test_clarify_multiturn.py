from __future__ import annotations

import pytest

from src.agent.clarify_helpers import (
    apply_clarify_option,
    build_employee_clarify,
    build_scope_clarify,
    is_vague_lookup_question,
    match_clarify_option,
)
from src.agent.graph import run_agent
from src.agent.resolver import EmployeeLookupResult
from src.db.session import AsyncSessionLocal


def test_employee_lookup_clarify_payload_structured():
    result = EmployeeLookupResult(
        kind="ambiguous",
        candidates=[
            {"姓名": "王伟", "工号": "A0210", "事业部": "杭综部门", "部门": "渠道组"},
            {"姓名": "王伟", "工号": "A0455", "事业部": "职能部门", "部门": "财务"},
        ],
    )
    clarify = result.clarify_payload("王伟")
    assert clarify["kind"] == "employee"
    assert "2 位" in clarify["question"]
    assert len(clarify["options"]) == 2
    assert clarify["options"][0]["value"] == "A0210"


def test_build_scope_clarify():
    clarify = build_scope_clarify("张三")
    assert clarify["kind"] == "scope"
    assert len(clarify["options"]) >= 3


def test_is_vague_lookup_question():
    assert is_vague_lookup_question("李四最近怎么样")
    assert not is_vague_lookup_question("李四11月请了几天假")


def test_match_clarify_option_by_employee_id():
    history = [
        {
            "question": "王伟最近怎么样",
            "intent": "lookup",
            "clarify": build_employee_clarify(
                "王伟",
                [
                    {"姓名": "王伟", "工号": "A0210", "事业部": "杭综部门", "部门": "渠道组"},
                    {"姓名": "王伟", "工号": "A0455", "事业部": "职能部门", "部门": "财务"},
                ],
            ),
        }
    ]
    opt = match_clarify_option("A0210", history)
    assert opt is not None
    assert opt["value"] == "A0210"


def test_apply_clarify_option_scope():
    entities = apply_clarify_option(
        {"employee": {"姓名": "李四", "工号": "A0145"}},
        {"label": "综合近况", "value": "overview", "lookup_scope": "overview"},
    )
    assert entities["lookup_scope"] == "overview"
    assert entities["target_l3"] == ["l3-5-1-1", "l3-2-2-1", "l3-2-2-4"]


@pytest.mark.asyncio
async def test_vague_lookup_returns_scope_clarify():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="李四最近怎么样", role="viewer")
    assert result["intent"] == "lookup"
    clarify = result.get("clarify") or {}
    assert clarify.get("kind") == "scope"
    assert any(opt.get("value") == "overview" for opt in (clarify.get("options") or []))


@pytest.mark.asyncio
async def test_clarify_followup_overview_answer():
    history = [
        {
            "question": "李四最近怎么样",
            "intent": "lookup",
            "entities": {"employee": {"姓名": "李四", "工号": "A0145", "事业部": "杭抖部门", "部门": "产品组"}},
            "clarify": {
                "kind": "scope",
                "question": "您想了解 李四 的哪方面？",
                "options": [
                    {"label": "综合近况（绩效+请假+加班）", "value": "overview", "lookup_scope": "overview"},
                ],
            },
        }
    ]
    async with AsyncSessionLocal() as db:
        result = await run_agent(
            db,
            question="综合近况（绩效+请假+加班）",
            role="viewer",
            history=history,
            entities={
                "employee": {"姓名": "李四", "工号": "A0145", "事业部": "杭抖部门", "部门": "产品组"},
                "lookup_scope": "overview",
                "target_l3": ["l3-5-1-1", "l3-2-2-1", "l3-2-2-4"],
            },
        )
    assert not result.get("clarify")
    assert result.get("answer")
    assert result.get("entities", {}).get("lookup_scope") == "overview"


@pytest.mark.asyncio
async def test_run_agent_returns_entities():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="张三11月请了几天假", role="viewer")
    entities = result.get("entities") or {}
    assert entities.get("employee", {}).get("工号") == "A0123"
