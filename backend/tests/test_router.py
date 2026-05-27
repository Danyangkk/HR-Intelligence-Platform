from __future__ import annotations

import pytest

from tests.router_harness import assert_router_expectations, load_router_cases, run_planner_for_case

ROUTER_CASES = load_router_cases()
ROUTER_CASE_IDS = [case["id"] for case in ROUTER_CASES]


@pytest.mark.parametrize("case", ROUTER_CASES, ids=ROUTER_CASE_IDS)
@pytest.mark.offline
def test_router_offline(case: dict) -> None:
    """CI 门禁：离线契约模式（录制 LLM 响应 + 规则引擎），只测 Planner。"""
    result = run_planner_for_case(case, offline=True)
    assert_router_expectations(result, case.get("expect") or {}, case_id=case["id"])


@pytest.mark.parametrize(
    "case_id",
    ["chat-hello", "agg-hangzong-headcount", "reject-person-salary", "lookup-leave"],
    ids=lambda x: x,
)
@pytest.mark.online
def test_router_online_smoke(case_id: str) -> None:
    """手动冒烟：真调 LLM，不进 CI 门禁。"""
    case = next(item for item in ROUTER_CASES if item["id"] == case_id)
    result = run_planner_for_case(case, offline=False)
    assert_router_expectations(result, case.get("expect") or {}, case_id=case_id)
