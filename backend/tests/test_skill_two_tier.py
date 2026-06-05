"""PR8 two-tier skill disclosure — mapping table + build_skill_context shape."""

from __future__ import annotations

import pytest

from src.agent.llm_runner import build_skill_context
from src.agent.skills.loader import primary_skills_for, skills_for_agent


@pytest.mark.parametrize(
    ("agent", "subtask_type", "intent", "retrieve_mode", "expected"),
    [
        ("Resolver", "resolve", "lookup", None, ["entity-resolution"]),
        ("Retriever", "retrieve", "aggregate", "structured", ["structured-retrieval"]),
        ("Retriever", "retrieve", "policy", "rag", ["document-rag"]),
        ("Analyst", "analyze", "trend", None, ["trend-analysis"]),
        ("Analyst", "analyze", "compare", None, ["compare-benchmark"]),
        ("Analyst", "analyze", "forecast", None, ["trend-analysis"]),
        ("Critic", "critique", "compare", None, ["evidence-validation"]),
        ("Composer", "compose", "policy", None, ["answer-composition"]),
    ],
)
def test_primary_skills_for_mapping_table(
    agent: str,
    subtask_type: str,
    intent: str,
    retrieve_mode: str | None,
    expected: list[str],
):
    assert (
        primary_skills_for(agent, subtask_type, intent, retrieve_mode) == expected
    )


def test_primary_skills_for_attribution_includes_process_skill():
    ids = primary_skills_for("Analyst", "analyze", "attribution", None)
    assert ids[0] == "attribution-methodology"
    assert len(ids) == 2
    assert ids[1].startswith("process-")


def test_build_skill_context_summary_line_count():
    state = {"intent": "compare", "plan": [], "plan_index": 0}
    ctx = build_skill_context("Analyst", state, subtask_type="analyze")
    bound = skills_for_agent("Analyst", intent="compare", subtask_type="analyze")
    summary_section = ctx.split("[本步骤执行规范]")[0]
    summary_lines = [line for line in summary_section.splitlines() if line.startswith("- ")]
    assert len(summary_lines) == len(bound)


def test_build_skill_context_includes_full_sop_tail():
    state = {"intent": "attribution", "plan": [], "plan_index": 0}
    ctx = build_skill_context("Analyst", state, subtask_type="analyze")
    assert "区分相关/因果" in ctx
    assert "主因加班强度偏高与薪酬竞争力偏低" in ctx
    assert "=== attribution-methodology（全文）===" in ctx


def test_build_skill_context_retriever_uses_rag_primary():
    state = {
        "intent": "policy",
        "plan": [{"type": "retrieve", "retrieve_mode": "rag"}],
        "plan_index": 0,
    }
    ctx = build_skill_context("Retriever", state, subtask_type="retrieve")
    assert "=== document-rag（全文）===" in ctx
    assert "=== structured-retrieval（全文）===" not in ctx
