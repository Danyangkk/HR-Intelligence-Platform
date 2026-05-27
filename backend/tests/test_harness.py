from __future__ import annotations

import asyncio

import pytest

from src.agent.harness.constants import FLOW_TIMEOUT_MESSAGE, MAX_RETRY, NODE_TIMEOUT_S, RETRY_BACKOFF_S
from src.agent.harness.context import infer_outcome, question_hash
from src.agent.harness.decision import extract_decision, sanitize_decision
from src.agent.harness.wrapper import is_business_terminal, node_failure_fallback, with_harness


def test_question_hash_not_plaintext():
    q = "张三的工资条是多少"
    hashed = question_hash(q)
    assert hashed != q
    assert len(hashed) == 64


def test_sanitize_decision_strips_sensitive_payload():
    raw = {
        "rows_returned": 2,
        "rows": [{"姓名": "张三", "实发合计": 12000}],
        "text": "制度正文不应出现",
        "chunk": "段落内容",
    }
    cleaned = sanitize_decision(raw)
    assert "rows" not in cleaned
    assert "text" not in cleaned
    assert "chunk" not in cleaned
    assert cleaned.get("rows_returned") == 2


def test_extract_decision_document_chunks_hit_only():
    decision = extract_decision(
        "document",
        {"evidence": [{"kind": "documents", "hits": [{"text": "secret", "score": 0.9}]}]},
        {"current_subtask": {"target_l3": ["l3-1-1-1"]}},
    )
    assert decision.get("chunks_hit") == 1
    assert "text" not in str(decision)


def test_infer_outcome_variants():
    assert infer_outcome({"short_circuit": True, "intent": "chitchat"})[0] == "success"
    assert infer_outcome({"rejected": True, "reject_reason": "个人薪资明细"})[0] == "reject"
    assert infer_outcome({"clarify": {"kind": "employee"}})[0] == "clarify"
    assert infer_outcome({}, flow_timeout=True)[0] == "timeout"


def test_is_business_terminal():
    assert is_business_terminal({"short_circuit": True})
    assert is_business_terminal({"rejected": True})
    assert is_business_terminal({"clarify": {"kind": "employee"}})
    assert not is_business_terminal({"plan": []})


@pytest.mark.asyncio
async def test_with_harness_no_retry_on_reject():
    calls = {"n": 0}

    async def planner_node(state, config):
        calls["n"] += 1
        return {"rejected": True, "reject_reason": "个人薪资明细", "final": "blocked"}

    wrapped = with_harness(planner_node, name="planner", timeout=1, max_retry=MAX_RETRY, retryable=True)
    out = await wrapped({"question": "x"}, {"configurable": {}})
    assert out["rejected"] is True
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_with_harness_retries_timeout(monkeypatch):
    calls = {"n": 0}

    async def slow_node(state, config):
        calls["n"] += 1
        if calls["n"] < 3:
            raise asyncio.TimeoutError()
        return {"ok": True}

    async def fast_wait_for(coro, *, timeout):
        return await coro

    monkeypatch.setattr("src.agent.harness.wrapper.asyncio.wait_for", fast_wait_for)
    monkeypatch.setattr("src.agent.harness.wrapper.RETRY_BACKOFF_S", (0.0, 0.0))

    wrapped = with_harness(slow_node, name="retrieve", timeout=NODE_TIMEOUT_S, max_retry=MAX_RETRY, retryable=True)
    out = await wrapped({}, {"configurable": {}})
    assert out.get("ok") is True
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_with_harness_exhausted_returns_fallback(monkeypatch):
    async def always_fail(state, config):
        await asyncio.sleep(0)
        raise RuntimeError("db down")

    async def fast_wait_for(coro, *, timeout):
        return await coro

    monkeypatch.setattr("src.agent.harness.wrapper.asyncio.wait_for", fast_wait_for)
    monkeypatch.setattr("src.agent.harness.wrapper.RETRY_BACKOFF_S", (0.0, 0.0))

    wrapped = with_harness(always_fail, name="composer", timeout=1, max_retry=MAX_RETRY, retryable=True)
    out = await wrapped({}, {"configurable": {}})
    assert out.get("final") == "系统繁忙，请稍后重试"


def test_node_failure_fallback_retriever_advances_plan():
    state = {"plan_index": 0, "plan": [{"id": "ST2", "type": "retrieve"}]}
    out = node_failure_fallback("retrieve", state, error_type="timeout")
    assert out.get("plan_index") == 1


def test_flow_timeout_message():
    assert "超时" in FLOW_TIMEOUT_MESSAGE
