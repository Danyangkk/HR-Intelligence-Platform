from __future__ import annotations

import asyncio

import pytest

from src.agent.stream import _planner_direct_reply, run_agent_stream
from src.db.session import AsyncSessionLocal


def test_planner_direct_reply_chitchat():
    out = _planner_direct_reply(
        {
            "intent": "chitchat",
            "plan": [],
            "final": "你好呀～我是 HR 的超级助手，今天有什么事情可以帮你呢？",
        }
    )
    assert out == ("chitchat", "你好呀～我是 HR 的超级助手，今天有什么事情可以帮你呢？")


def test_planner_direct_reply_unmatched():
    out = _planner_direct_reply(
        {
            "unmatched": True,
            "final": "抱歉哦～ 我没有查到问题的相关答案，可以换个问题试试看呢。",
        }
    )
    assert out and out[0] == "unmatched"


@pytest.mark.asyncio
async def test_stream_chitchat_emits_answer_not_plan():
    events: list[str] = []
    async with AsyncSessionLocal() as db:
        async for chunk in run_agent_stream(db, question="你好", role="hr_admin"):
            for line in chunk.strip().split("\n"):
                if line.startswith("event:"):
                    events.append(line.split(":", 1)[1].strip())
    assert "answer" in events
    assert "plan" not in events
    assert events[-1] == "done"
