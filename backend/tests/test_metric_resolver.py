from __future__ import annotations

from src.agent.metric_resolver import resolve_metric_from_text


def test_resolve_performance_poor():
    spec = resolve_metric_from_text("张三为什么绩效很差", "绩效很差")
    assert spec is not None
    assert spec["name"] == "绩效分布偏离"
    assert spec["benchmark"]
    assert spec["threshold"]


def test_resolve_turnover_high():
    spec = resolve_metric_from_text("为什么运营组离职率偏高", "")
    assert spec is not None
    assert spec["name"] == "离职率"


def test_resolve_cost_high():
    spec = resolve_metric_from_text("对比各事业部人均成本谁高", "成本高")
    assert spec is not None
    assert "成本" in spec["name"]
