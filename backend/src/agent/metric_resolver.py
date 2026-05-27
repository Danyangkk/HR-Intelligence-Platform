"""Map fuzzy metric phrases to metrics_dictionary entries (Resolver validation layer)."""

from __future__ import annotations

import re
from typing import Any

from src.services.metrics.dictionary import MetricDefinition, get_metric, search_metrics

# (keyword groups, metric name in dictionary)
_FUZZY_METRIC_RULES: list[tuple[tuple[str, ...], str]] = [
    (("绩效", "很差"), "绩效分布偏离"),
    (("绩效", "较差"), "绩效分布偏离"),
    (("绩效", "差"), "绩效分布偏离"),
    (("绩效", "偏低"), "绩效分布偏离"),
    (("成本", "高"), "人均人力成本"),
    (("人均成本", "高"), "人均人力成本"),
    (("离职率", "偏高"), "离职率"),
    (("离职率", "高"), "离职率"),
    (("离职", "偏高"), "离职率"),
    (("出勤", "低"), "出勤率"),
    (("加班", "高"), "人均加班时长"),
]

_BENCHMARK_DEFAULTS: dict[str, str] = {
    "绩效分布偏离": "同部门同岗均值",
    "人均人力成本": "事业部均值",
    "离职率": "公司/同事业部均值",
    "出勤率": "部门均值",
    "人均加班时长": "部门均值",
}

_THRESHOLD_PATTERNS: list[tuple[str, str]] = [
    (r"低于均值×([\d.]+)", "低于均值×\\1"),
    (r"低于1个标准差", "低于1个标准差"),
    (r"高于均值×([\d.]+)", "高于均值×\\1"),
]


def _threshold_from_notes(defn: MetricDefinition) -> str:
    notes = defn.notes or ""
    if "绩效差" in notes or "显著低于" in notes:
        return "低于均值×0.85 或低于1个标准差"
    if "偏高" in notes or "高于" in notes:
        return "高于同口径基准"
    for pattern, template in _THRESHOLD_PATTERNS:
        m = re.search(pattern, notes)
        if m:
            return template.replace("\\1", m.group(1)) if m.lastindex else template
    return ""


def metric_spec_from_definition(defn: MetricDefinition) -> dict[str, Any]:
    benchmark = defn.benchmark or _BENCHMARK_DEFAULTS.get(defn.name, "同口径基准")
    threshold = defn.threshold or _threshold_from_notes(defn)
    citation = defn.citation or defn.formula
    return {
        "id": defn.id,
        "name": defn.name,
        "formula": defn.formula,
        "benchmark": benchmark,
        "threshold": threshold,
        "citation": citation,
        "inputs": list(defn.inputs),
    }


def resolve_metric_from_text(question: str, metric_query: str = "") -> dict[str, Any] | None:
    """Resolve fuzzy metric phrase to dictionary-backed entities.metric."""
    haystacks = [metric_query.strip(), question.strip()]
    haystacks = [h for h in haystacks if h]

    for text in haystacks:
        for keywords, metric_name in _FUZZY_METRIC_RULES:
            if all(k in text for k in keywords):
                defn = get_metric(metric_name)
                if defn:
                    return metric_spec_from_definition(defn)

    for text in haystacks:
        hits = search_metrics(text, limit=3)
        if hits:
            defn = get_metric(str(hits[0].get("name") or ""))
            if defn:
                return metric_spec_from_definition(defn)

    # Single explicit metric name in question
    for text in haystacks:
        for token in ("离职率", "人均人力成本", "绩效分布偏离", "出勤率", "人均加班时长"):
            if token in text:
                defn = get_metric(token)
                if defn:
                    return metric_spec_from_definition(defn)

    return None
