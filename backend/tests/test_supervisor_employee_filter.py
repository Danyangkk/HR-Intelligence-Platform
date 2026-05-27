from __future__ import annotations

import pytest

from src.agent.supervisor import (
    _filter_rows_for_employee,
    _filters_for_l3,
    _retrieve_worker_payload,
    supervisor_dispatch,
)


def test_retrieve_worker_payload_carries_entities():
    state = {
        "question": "王五为什么绩效很差",
        "intent": "attribution",
        "role": "viewer",
        "entities": {"employee": {"工号": "A0188", "姓名": "王五", "部门": "运营组"}},
        "plan_index": 1,
        "plan": [
            {"id": "ST1", "type": "resolve", "assigned_agent": "Resolver"},
            {
                "id": "ST2",
                "type": "retrieve",
                "retrieve_mode": "structured",
                "target_l3": ["l3-5-1-1", "l3-2-2-4"],
                "assigned_agent": "Retriever",
            },
        ],
    }
    payload = _retrieve_worker_payload(state, "l3-2-2-4")
    assert payload["fetch_l3_id"] == "l3-2-2-4"
    assert payload["entities"]["employee"]["工号"] == "A0188"
    assert payload["intent"] == "attribution"


def test_supervisor_send_includes_entities_for_parallel_retrieve():
    state = {
        "question": "王五为什么绩效很差",
        "intent": "attribution",
        "role": "viewer",
        "entities": {"employee": {"工号": "A0188", "姓名": "王五"}},
        "plan_index": 1,
        "plan": [
            {"id": "ST1", "type": "resolve", "assigned_agent": "Resolver"},
            {
                "id": "ST2",
                "type": "retrieve",
                "retrieve_mode": "structured",
                "target_l3": ["l3-5-1-1", "l3-2-2-4"],
                "assigned_agent": "Retriever",
            },
        ],
    }
    route = supervisor_dispatch(state)
    assert isinstance(route, list)
    assert len(route) == 2
    assert route[0].arg["entities"]["employee"]["工号"] == "A0188"


def test_filters_for_l3_applies_employee_id_on_change_records():
    state = {
        "intent": "attribution",
        "entities": {"employee": {"工号": "A0188", "姓名": "王五"}},
    }
    assert _filters_for_l3(state, "l3-2-3-1") == {"工号": "A0188"}


def test_filter_rows_for_employee_removes_other_people():
    state = {
        "intent": "attribution",
        "entities": {"employee": {"工号": "A0188", "姓名": "王五"}},
    }
    rows = [
        {"工号": "A0188", "加班日期": "2025-11-10"},
        {"工号": "A0245", "加班日期": "2025-11-03"},
    ]
    filtered = _filter_rows_for_employee(state, "l3-2-2-4", rows)
    assert len(filtered) == 1
    assert filtered[0]["工号"] == "A0188"


@pytest.mark.asyncio
async def test_wangwu_attribution_citations_only_self():
    from src.agent.graph import run_agent
    from src.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await run_agent(db, question="王五为什么绩效很差", role="viewer")
    emp_id = (result.get("entities") or {}).get("employee", {}).get("工号")
    assert emp_id == "A0188"
    for cite in result.get("citations") or []:
        if cite.get("kind") != "data":
            continue
        l3 = cite.get("l3_id")
        if l3 not in {"l3-2-2-1", "l3-2-2-4", "l3-2-3-1", "l3-5-1-1", "l3-5-2-1"}:
            continue
        for key in cite.get("locator") or []:
            if key.get("field") == "工号":
                assert key.get("value") == "A0188", f"{l3} cited {key.get('value')}"
