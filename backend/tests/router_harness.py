from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.agent.planner import run_planner

CASES_PATH = Path(__file__).resolve().parent / "router_cases.yaml"
RECORDINGS_DIR = Path(__file__).resolve().parent / "fixtures" / "llm_recordings"


def load_router_cases() -> list[dict[str, Any]]:
    raw = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("router_cases.yaml must be a list")
    return raw


def build_planner_state(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": case["query"],
        "history": case.get("history") or [],
        "role": "viewer",
        "entities": {},
        "plan": [],
        "evidence": [],
        "trace": [],
        "replan_count": 0,
    }


def load_llm_recording(case_id: str) -> dict[str, Any] | None:
    path = RECORDINGS_DIR / f"{case_id}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def collect_path_markers(plan: list[dict[str, Any]]) -> set[str]:
    markers: set[str] = set()
    for item in plan:
        mode = item.get("retrieve_mode")
        if mode == "rag":
            markers.add("rag")
        if mode == "structured":
            markers.add("structured")
        targets = item.get("target_l3") or []
        if any(str(t).startswith("l3-1-") for t in targets):
            markers.add("policy")
    return markers


def run_planner_for_case(case: dict[str, Any], *, offline: bool = True) -> dict[str, Any]:
    """Run Planner only; offline mode uses recordings then rules fallback."""
    from unittest.mock import patch

    from src.agent import planner_llm

    case_id = case["id"]

    def _llm_stub(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
        if offline:
            return load_llm_recording(case_id)
        return planner_llm.plan_with_llm(*args, **kwargs)

    with patch.object(planner_llm, "plan_with_llm", _llm_stub):
        return run_planner(build_planner_state(case))


def assert_router_expectations(result: dict[str, Any], expect: dict[str, Any], *, case_id: str = "") -> None:
    plan = result.get("plan") or []
    subtask_types = {str(item.get("type")) for item in plan if item.get("type")}
    assigned_agents = {str(item.get("assigned_agent")) for item in plan if item.get("assigned_agent")}
    path_markers = collect_path_markers(plan)

    if expect.get("reject"):
        assert result.get("rejected") is True, f"{case_id}: expected reject"
        if expect.get("no_subtasks"):
            assert not plan, f"{case_id}: reject should have no subtasks"
        return

    assert result.get("rejected") is not True or result.get("unmatched"), f"{case_id}: unexpected reject"

    if "intent" in expect:
        assert result.get("intent") == expect["intent"], (
            f"{case_id}: intent expected {expect['intent']}, got {result.get('intent')}"
        )

    if expect.get("chitchat") is True:
        assert result.get("short_circuit") is True, f"{case_id}: expected chitchat short_circuit"
        assert result.get("intent") == "chitchat", f"{case_id}: chitchat intent"
        assert bool(result.get("final")), f"{case_id}: chitchat should have reply"
    elif expect.get("chitchat") is False:
        assert result.get("short_circuit") is not True, f"{case_id}: should not chitchat short-circuit"

    if expect.get("no_subtasks"):
        assert not plan, f"{case_id}: expected no subtasks"

    must_types = expect.get("must_have_subtask_types") or []
    for stype in must_types:
        assert stype in subtask_types, f"{case_id}: missing subtask type {stype} in {subtask_types}"

    for forbidden in expect.get("forbid_path") or []:
        assert forbidden not in path_markers, f"{case_id}: forbidden path {forbidden} in {path_markers}"

    subset = expect.get("assigned_agents_subset") or []
    for agent in subset:
        assert agent in assigned_agents, f"{case_id}: missing assigned agent {agent} in {assigned_agents}"
