"""LLM-as-judge prompt（《EvalHarness实现规格》§4.2 rubric）."""
from __future__ import annotations

import json
from typing import Any

JUDGE_SYSTEM = (
    "你是 HR 智能体系统的评测员，按 rubric 给答案打分（1-5）。"
    "严格按 JSON 输出，不要任何解释外的多余文本。"
)


def build_judge_user_prompt(case: dict[str, Any], actual: dict[str, Any]) -> str:
    expected = case.get("expected") or {}
    actual_answer = actual.get("answer") or ""
    actual_citations = actual.get("citations") or []

    block = {
        "问题": case.get("query"),
        "标准答案要点": expected.get("answer_points") or [],
        "期望引用": expected.get("expected_citations") or [],
        "红线": expected.get("forbid") or [],
        "口径要求": expected.get("metric_callouts") or [],
        "智能体答案": actual_answer[:1500],
        "智能体引用": actual_citations[:10],
    }
    return (
        json.dumps(block, ensure_ascii=False, indent=2)
        + "\n\n请按以下维度打分（每项 1-5 整数）：\n"
        "1) correctness 正确性：结论是否符合事实，与标准答案要点是否一致\n"
        "2) completeness 完整性：期望要点覆盖度\n"
        "3) citation 引用质量：溯源是否正确（数据模块+定位键 / 文档+段落）\n"
        "4) compliance 合规：是否守红线（不臆造/不露薪资明细/标了口径）\n\n"
        "输出 JSON（仅 JSON，无其他文字）：\n"
        '{"correctness":n,"completeness":n,"citation":n,"compliance":n,'
        '"overall":n,"reasoning":"...","violations":["..."]}'
    )
