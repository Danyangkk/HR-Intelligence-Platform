"""Eval 覆盖矩阵与 expected 完备度（PR6）。"""
from __future__ import annotations

from typing import Any

from src.eval.loader import load_eval_set

EVAL_INTENTS: tuple[str, ...] = (
    "chitchat",
    "policy",
    "lookup",
    "list",
    "aggregate",
    "trend",
    "forecast",
    "compare",
    "attribution",
)

LAYER_COLUMNS: tuple[int, ...] = (1, 2, 3)

COMPLETENESS_FIELDS: tuple[str, ...] = ("answer_points", "forbid", "metric_callouts")

# 意图 → 必填 expected 字段（不适用的不算欠账）
REQUIRED_FIELDS_BY_INTENT: dict[str, frozenset[str]] = {
    "chitchat": frozenset(),
    "lookup": frozenset({"answer_points", "forbid"}),
    "list": frozenset({"answer_points", "forbid"}),
    "policy": frozenset({"answer_points", "forbid", "metric_callouts"}),
    "aggregate": frozenset({"answer_points", "forbid", "metric_callouts"}),
    "trend": frozenset({"answer_points", "forbid", "metric_callouts"}),
    "compare": frozenset({"answer_points", "forbid", "metric_callouts"}),
    "forecast": frozenset({"answer_points", "forbid", "metric_callouts"}),
    "attribution": frozenset({"answer_points", "forbid", "metric_callouts"}),
}

FIELD_LABELS: dict[str, str] = {
    "answer_points": "answer_points",
    "forbid": "forbid",
    "metric_callouts": "metric_callouts",
}

FIELD_HINTS: dict[str, str] = {
    "answer_points": "grader 完整性评分无参照",
    "forbid": "合规红线维度无法检查",
    "metric_callouts": "口径标注无人校验",
}


def required_fields_for_intent(intent: str | None) -> frozenset[str]:
    if not intent:
        return frozenset(COMPLETENESS_FIELDS)
    return REQUIRED_FIELDS_BY_INTENT.get(intent, frozenset(COMPLETENESS_FIELDS))


def build_eval_coverage(path=None) -> dict[str, Any]:
    """基于 eval_set.yaml 统计意图×层矩阵与 expected 字段完备度。"""
    cases = load_eval_set(path)
    matrix: dict[str, dict[str, int]] = {
        intent: {f"L{layer}": 0 for layer in LAYER_COLUMNS} for intent in EVAL_INTENTS
    }

    missing: dict[str, list[str]] = {field: [] for field in COMPLETENESS_FIELDS}

    for case in cases:
        intent = (case.get("expected") or {}).get("intent") or "unknown"
        if intent not in matrix:
            matrix[intent] = {f"L{layer}": 0 for layer in LAYER_COLUMNS}
        for layer in case.get("layer") or []:
            key = f"L{int(layer)}"
            if key in matrix[intent]:
                matrix[intent][key] += 1

        if 3 not in (case.get("layer") or []):
            continue
        expected = case.get("expected") or {}
        applicable = required_fields_for_intent(intent)
        for field in COMPLETENESS_FIELDS:
            if field not in applicable:
                continue
            value = expected.get(field)
            if not value:
                missing[field].append(case["id"])

    groups = []
    for field in COMPLETENESS_FIELDS:
        ids = missing[field]
        groups.append(
            {
                "field": field,
                "label": FIELD_LABELS[field],
                "hint": FIELD_HINTS[field],
                "missing": ids,
                "count": len(ids),
                "complete": len(ids) == 0,
            }
        )

    complete = all(g["complete"] for g in groups)
    return {
        "intents": list(EVAL_INTENTS),
        "layers": [f"L{layer}" for layer in LAYER_COLUMNS],
        "matrix": matrix,
        "completeness": {
            "complete": complete,
            "missing": missing,
            "groups": groups,
        },
        "total_cases": len(cases),
    }
