from __future__ import annotations

from src.agent.planner_llm import _planner_system_prompt
from src.agent.prompts.agents import PLANNER_SYSTEM
from src.agent.router_loader import inject_router, load_router


def test_router_md_exists_and_has_main_table():
    router = load_router()
    assert "意图 → 激活阶段 → skills 推荐拆法" in router
    assert "chitchat" in router
    assert "attribution" in router
    assert "policy 白名单" in router


def test_planner_system_has_router_placeholder():
    assert "{{router}}" in PLANNER_SYSTEM
    assert "映射规则" not in PLANNER_SYSTEM
    assert "主体=组织 且 想要=统计数值" not in PLANNER_SYSTEM


def test_planner_prompt_injects_router_full_text():
    prompt = _planner_system_prompt()
    router = load_router()
    assert router in prompt
    assert "{{router}}" not in prompt
    assert "intent-planning" not in prompt.lower() or "ROUTER.md" in prompt


def test_planner_prompt_no_duplicate_intent_mapping_table():
    prompt = _planner_system_prompt()
    assert "语义映射（必须遵守）" not in prompt
    assert "计划模板（按 intent 选用）" not in prompt
    assert prompt.count("意图 → 激活阶段 → skills 推荐拆法") == 1


def test_inject_router_replaces_placeholder():
    out = inject_router("before {{router}} after", router="ROUTER_BODY")
    assert out == "before ROUTER_BODY after"
