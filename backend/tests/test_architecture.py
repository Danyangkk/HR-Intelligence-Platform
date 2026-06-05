from __future__ import annotations

import pytest

from src.agent.skills.runner import begin_agent_run
from src.agent.supervisor import get_current_subtask, route_after_supervisor, supervisor_dispatch
from src.agent.tools.registry import TOOL_NAMES, call_tool, tool_calc, tool_chart_render, tool_pii_check
from src.services.feishu.config_status import feishu_table_config_status
from src.services.feishu.mappings import get_sync_config, list_feishu_sync_l3_ids


def test_tool_registry_has_eight_tools():
    assert len(TOOL_NAMES) == 8
    assert "query_structured" in TOOL_NAMES
    assert "search_documents" in TOOL_NAMES
    assert "chart_render" in TOOL_NAMES


def test_tool_pii_check_viewer():
    result = tool_pii_check("viewer", "l3-2-2-1", ["姓名", "身份证号"])
    assert result["field_access"]["姓名"] == "allow"
    assert result["field_access"]["身份证号"] == "mask"


def test_tool_calc_turnover_rate():
    result = tool_calc(metric="离职率", inputs={"期间离职人数": 3, "期间平均在职人数": 42})
    assert result["value"] == pytest.approx(3 / 42, rel=1e-4)


def test_tool_chart_render():
    spec = {"type": "bar", "title": "test", "data": [{"name": "A", "value": 1}]}
    out = tool_chart_render(spec)
    assert out["rendered"] is True
    assert out["data"][0]["name"] == "A"


def test_supervisor_routes_plan_subtasks():
    state = {
        "plan": [
            {"id": "t1", "type": "resolve", "assigned_agent": "Resolver"},
            {"id": "t2", "type": "retrieve", "retrieve_mode": "structured", "assigned_agent": "Retriever"},
            {"id": "t3", "type": "compose", "assigned_agent": "Composer"},
        ],
        "plan_index": 0,
    }
    assert route_after_supervisor(state) == "resolver"
    state["plan_index"] = 1
    assert route_after_supervisor(state) == "retrieve"
    state["plan_index"] = 2
    assert route_after_supervisor(state) == "composer"


def test_supervisor_rag_retrieve_routes_document():
    state = {
        "plan": [{"id": "t1", "type": "retrieve", "retrieve_mode": "rag", "assigned_agent": "Retriever"}],
        "plan_index": 0,
    }
    assert route_after_supervisor(state) == "document"
    assert get_current_subtask(state)["retrieve_mode"] == "rag"


def test_feishu_sync_registry_covers_eleven_tables():
    ids = list_feishu_sync_l3_ids()
    assert len(ids) == 11
    for l3_id in ids:
        assert get_sync_config(l3_id) is not None


def test_call_tool_calc_matches_tool_calc():
    inputs = {"期间离职人数": 3, "期间平均在职人数": 42}
    assert call_tool("calc", metric="离职率", inputs=inputs) == tool_calc(metric="离职率", inputs=inputs)


def test_supervisor_send_fanout_for_multi_table_retrieve():
    state = {
        "intent": "compare",
        "plan": [
            {
                "id": "t2",
                "type": "retrieve",
                "retrieve_mode": "structured",
                "target_l3": ["l3-4-6-3", "l3-6-1-1"],
                "assigned_agent": "Retriever",
            }
        ],
        "plan_index": 0,
    }
    dispatch = supervisor_dispatch(state)
    assert isinstance(dispatch, list)
    assert len(dispatch) == 2
    assert {s.node for s in dispatch} == {"retrieve_worker"}


def test_skill_runner_executes_sop_steps():
    ctx = begin_agent_run("Analyst", {"intent": "compare"}, subtask_type="analyze")
    ctx.run_step("compare-benchmark", 1, "识别对比维度")
    ctx.record_tool("calc")
    patch = ctx.to_state_patch()
    assert patch["active_skills"]
    assert patch["sop_executed"][0]["skill_id"] == "compare-benchmark"
    entry = ctx.trace_entry(subtask_id="analyst", summary="done")
    assert entry["tools"] == ["calc"]
    assert entry["sop"]


def test_all_agents_load_skills_from_skill_md():
    # Planner deliberately has no SKILL.md bindings (trace label only: intent-planning).
    for agent, subtask in [
        ("Resolver", "resolve"),
        ("Retriever", "retrieve"),
        ("Analyst", "analyze"),
        ("Critic", "critique"),
        ("Composer", "compose"),
    ]:
        ctx = begin_agent_run(agent, {"intent": "lookup"}, subtask_type=subtask)
        assert ctx.skills, f"{agent} should load skills"
        assert ctx.skills[0].get("content"), f"{agent} SKILL.md content missing"


def test_planner_has_no_bound_skills_by_design():
    ctx = begin_agent_run("Planner", {"intent": "lookup"})
    assert ctx.skills == []


def test_planner_trace_includes_sop():
    from src.agent.planner import run_planner

    state = run_planner({"question": "张三11月请了几天假"})
    trace = state["trace"][0]
    assert trace.get("sop")
    assert trace.get("skill")
    assert state["intent"] == "lookup"


def test_feishu_config_status_reports_eleven_tables():
    status = feishu_table_config_status()
    assert status["total_tables"] == 11
    assert len(status["tables"]) == 11
    assert "all_configured" in status
