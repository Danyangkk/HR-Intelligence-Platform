from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models import AgentFeedback, AgentRun
from src.services.agent_feedback import list_badcases, submit_agent_feedback, update_badcase_review
from src.services.harness_trace import resolve_auto_badcase


def test_resolve_auto_badcase_timeout_and_clarify():
    flagged, reason = resolve_auto_badcase(outcome="timeout", signals=[])
    assert flagged is True
    assert reason == "timeout"

    flagged, reason = resolve_auto_badcase(outcome="clarify", signals=["rag_zero_hit"])
    assert flagged is True
    assert "clarify" in reason
    assert "rag_zero_hit" in reason


@pytest.mark.asyncio
async def test_submit_feedback_and_badcase_review():
    from src.db.session import AsyncSessionLocal

    run_id = uuid.uuid4()
    badcase_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(
            AgentRun(
                id=run_id,
                session_id="sess-fb-1",
                role="viewer",
                question_hash="abc",
                intent="lookup",
                outcome="success",
            )
        )
        db.add(
            AgentRun(
                id=badcase_id,
                session_id="sess-bc-1",
                role="viewer",
                question_hash="def",
                intent="policy",
                outcome="success",
                auto_badcase=True,
                badcase_reason="rag_zero_hit",
                review_status="pending",
            )
        )
        await db.commit()

        up = await submit_agent_feedback(db, run_id=str(run_id), rating="up")
        assert up["rating"] == "up"

        down = await submit_agent_feedback(db, run_id=str(run_id), rating="down", reason="wrong")
        assert down["reason"] == "wrong"

        run = await db.get(AgentRun, run_id)
        assert run is not None
        assert run.user_feedback == "down"
        assert run.auto_badcase is True
        assert run.badcase_reason == "user_down"

        rows = await db.scalars(
            __import__("sqlalchemy").select(AgentFeedback).where(AgentFeedback.run_id == run_id)
        )
        assert len(list(rows.all())) == 2

        listed = await list_badcases(db, role="hr_admin", page=1, page_size=10, status="pending")
        assert listed["total"] >= 1
        assert any(item["run_id"] == str(badcase_id) for item in listed["items"])

        updated = await update_badcase_review(
            db, role="hr_admin", run_id=str(badcase_id), review_status="fixed"
        )
        assert updated is not None
        assert updated["review_status"] == "fixed"

        denied = await list_badcases(db, role="viewer", page=1, page_size=10)
        assert denied["total"] == 0


@pytest.mark.asyncio
async def test_feedback_api_requires_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/agent/feedback",
            json={"run_id": str(uuid.uuid4()), "rating": "up"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["code"] != 0


@pytest.mark.asyncio
async def test_badcases_api_forbidden_for_viewer():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/agent/harness/badcases")
        assert res.status_code == 403
