from __future__ import annotations

from src.agent.planner import run_planner
from src.agent.planner_llm import plan_with_llm, plan_with_rules, resolve_plan
from src.agent.planner_rules import (
    CHITCHAT_CASUAL_REPLY,
    CHITCHAT_FAREWELL_REPLY,
    CHITCHAT_GREETING_REPLY,
    CHITCHAT_INTRO_REPLY,
    INTENT_UNMATCHED_MESSAGE,
    classify_chitchat,
    classify_intent,
    is_policy_question,
)


def test_classify_chitchat_greeting():
    out = classify_chitchat("你好")
    assert out and out["intent"] == "chitchat"
    assert out["reply"] == CHITCHAT_GREETING_REPLY


def test_classify_chitchat_intro():
    out = classify_chitchat("你能干嘛")
    assert out and out["reply"] == CHITCHAT_INTRO_REPLY


def test_classify_chitchat_farewell():
    out = classify_chitchat("再见")
    assert out and out["kind"] == "farewell"
    assert out["reply"] == CHITCHAT_FAREWELL_REPLY


def test_classify_chitchat_casual():
    out = classify_chitchat("今天天气怎么样")
    assert out and out["kind"] == "casual"
    assert out["reply"] == CHITCHAT_CASUAL_REPLY


def test_classify_chitchat_not_policy_question():
    assert classify_chitchat("年假怎么算") is None


def test_classify_intent_no_policy_fallback():
    assert classify_intent("今天天气怎么样") is None
    assert classify_intent("qwerty无效乱码") is None


def test_classify_intent_policy_still_works():
    assert classify_intent("年假怎么算") == "policy"
    assert classify_intent("离职需要做哪些动作") == "policy"


def test_is_policy_question():
    assert is_policy_question("年假怎么算") is True
    assert is_policy_question("今天天气怎么样") is False


def test_plan_with_rules_unmatched():
    out = plan_with_rules("qwerty无效乱码")
    assert out.get("unmatched") is True
    assert out.get("plan") == []


def test_resolve_plan_unmatched_when_rules_miss(monkeypatch):
    monkeypatch.setattr("src.agent.planner_llm.plan_with_llm", lambda *a, **k: None)
    out = resolve_plan("qwerty无效乱码")
    assert out.get("unmatched") is True


def test_plan_with_llm_low_confidence(monkeypatch):
    monkeypatch.setattr(
        "src.agent.planner_llm.chat_completion",
        lambda **k: '{"intent":"policy","confidence":0.2,"reasoning":"不确定","plan":[{"id":"ST1","type":"retrieve","goal":"x","assigned_agent":"Retriever","retrieve_mode":"rag","target_l3":["l3-1-1-1"]},{"id":"ST2","type":"compose","goal":"y","assigned_agent":"Composer"}]}',
    )
    out = plan_with_llm("今天天气怎么样")
    assert out and out.get("unmatched") is True


def test_plan_with_llm_rejects_policy_without_whitelist(monkeypatch):
    monkeypatch.setattr(
        "src.agent.planner_llm.chat_completion",
        lambda **k: '{"intent":"policy","confidence":0.9,"reasoning":"兜底","plan":[{"id":"ST1","type":"retrieve","goal":"x","assigned_agent":"Retriever","retrieve_mode":"rag","target_l3":["l3-1-1-1"]},{"id":"ST2","type":"compose","goal":"y","assigned_agent":"Composer"}]}',
    )
    out = plan_with_llm("今天天气怎么样")
    assert out and out.get("unmatched") is True


def test_run_planner_unmatched_message():
    state = run_planner({"question": "qwerty无效乱码"})
    assert state.get("unmatched") is True
    assert state.get("final") == INTENT_UNMATCHED_MESSAGE


def test_run_planner_chitchat_weather():
    state = run_planner({"question": "今天天气怎么样"})
    assert state.get("intent") == "chitchat"
    assert state.get("short_circuit") is True
    assert state.get("final") == CHITCHAT_CASUAL_REPLY


def test_run_planner_chitchat_short_circuit():
    state = run_planner({"question": "你好"})
    assert state.get("intent") == "chitchat"
    assert state.get("short_circuit") is True
    assert state.get("final") == CHITCHAT_GREETING_REPLY


def test_resolve_plan_chitchat_first():
    out = resolve_plan("你好")
    assert out.get("chitchat") is True
    assert out.get("reply") == CHITCHAT_GREETING_REPLY
