from __future__ import annotations

import pytest

from src.agent.graph import run_agent
from src.db.session import AsyncSessionLocal
from src.models import AgentRunLog, AuditLog
from sqlalchemy import select


@pytest.mark.asyncio
async def test_agent_run_persisted_with_audit():
    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="张三11月请了几天假", role="viewer", session_id="test-session-1")
        assert result["session_id"] == "test-session-1"
        from src.services.agent_runs import infer_tools_used, persist_agent_run
        from src.services.audit import write_audit

        await persist_agent_run(
            db,
            session_id=result["session_id"],
            actor="tester",
            role="viewer",
            question=result["question"],
            result=result,
            duration_ms=result["duration_ms"],
        )
        await write_audit(
            db,
            actor="tester",
            action="agent.ask",
            target_id=result["session_id"],
            detail={"tools_used": infer_tools_used(result.get("intent"), result.get("trace"))},
        )

    async with AsyncSessionLocal() as db:
        run = await db.scalar(select(AgentRunLog).where(AgentRunLog.session_id == "test-session-1"))
        assert run is not None
        assert run.intent == "lookup"
        assert isinstance(run.trace, list)
        assert isinstance(run.tools_used, list)

        audit = await db.scalar(select(AuditLog).where(AuditLog.target_id == "test-session-1"))
        assert audit is not None
        assert audit.action == "agent.ask"
