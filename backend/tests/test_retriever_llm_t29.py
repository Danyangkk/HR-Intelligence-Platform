from __future__ import annotations

import pytest

from src.agent.retriever_llm import rules_relaxed_filters
from src.agent.state import AgentState


def test_rules_relaxed_filters_drops_bu_on_l3_turnover():
    state: AgentState = {
        "intent": "aggregate",
        "broaden_search": False,
    }
    filters = {"事业部": "杭抖部门", "统计周期": "2025-10"}
    relaxed = rules_relaxed_filters(state, "l3-2-5-1", filters)
    assert relaxed == {"统计周期": "2025-10"}


def test_rules_relaxed_filters_skips_when_broaden_search():
    state: AgentState = {"intent": "aggregate", "broaden_search": True}
    filters = {"事业部": "杭抖部门", "统计周期": "2025-10"}
    assert rules_relaxed_filters(state, "l3-2-5-1", filters) is None
