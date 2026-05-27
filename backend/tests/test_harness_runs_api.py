from __future__ import annotations

import uuid

import pytest

from src.services.harness_runs import _serialize_node_trace, _serialize_run
from src.models import AgentNodeTrace, AgentRun


def test_serialize_run_excludes_sensitive_fields():
    run = AgentRun(
        id=uuid.uuid4(),
        session_id="sess-1",
        role="viewer",
        question_hash="abc123",
        intent="lookup",
        outcome="success",
        replan_count=0,
        node_count=2,
        total_ms=1200,
    )
    data = _serialize_run(run)
    assert data["question_hash"] == "abc123"
    assert "question" not in data
    assert data["run_id"] == str(run.id)


def test_serialize_node_trace_metadata_only():
    row = AgentNodeTrace(
        run_id=uuid.uuid4(),
        seq=1,
        node="retriever",
        agent="Retriever",
        skills_loaded=[{"id": "structured-retrieval", "name": "结构化取数"}],
        tools_called=[{"name": "query_structured"}],
        status="ok",
        attempt=1,
        duration_ms=45,
        decision={"rows_returned": 3, "path": "structured"},
    )
    data = _serialize_node_trace(row)
    assert data["decision"]["rows_returned"] == 3
    assert "rows" not in data["decision"]
