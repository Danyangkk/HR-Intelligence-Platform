from __future__ import annotations

import pytest

from src.services.metrics.calc import CalcError, calculate_metric, calculate_operation
from src.services.metrics.dictionary import get_metric, list_metrics, search_metrics


def test_dictionary_loads_appendix_d_metrics():
    items = list_metrics()
    assert len(items) >= 28
    names = {item["name"] for item in items}
    assert "离职率" in names
    assert "人均人力成本" in names


def test_get_turnover_rate_definition():
    metric = get_metric("离职率")
    assert metric is not None
    assert metric.formula == "期间离职人数 / 期间平均在职人数"
    assert "主动+被动" in metric.notes


def test_calculate_turnover_rate():
    result = calculate_metric(
        "离职率",
        {"期间离职人数": 5, "期间平均在职人数": 100},
    )
    assert result.value == pytest.approx(0.05)
    assert result.formatted == "5.00%"
    assert "离职率" in result.citation
    assert "期间离职人数 / 期间平均在职人数" in result.citation


def test_calculate_stability_rate_from_components():
    result = calculate_metric(
        "人员稳定率",
        {"期间离职人数": 5, "期间平均在职人数": 100},
    )
    assert result.value == pytest.approx(0.95)
    assert result.formatted == "95.00%"


def test_calculate_labor_cost_per_capita():
    result = calculate_metric(
        "人均人力成本",
        {"部门人力成本合计": 500000, "在职人数": 50},
    )
    assert result.value == pytest.approx(10000)
    assert "10,000.00" in result.formatted


def test_calculate_cost_mom():
    result = calculate_metric("成本环比", {"本期": 110, "上期": 100})
    assert result.value == pytest.approx(0.1)
    assert result.formatted == "10.00%"


def test_calculate_operation_ratio_with_metric_citation():
    result = calculate_operation(
        "ratio",
        numerator=3,
        denominator=12,
        metric="请假率",
    )
    assert result.value == pytest.approx(0.25)
    assert "请假率" in result.citation


def test_search_metrics():
    hits = search_metrics("离职")
    assert any(item["name"] == "离职率" for item in hits)


def test_unknown_metric_raises():
    with pytest.raises(CalcError, match="未知指标"):
        calculate_metric("不存在指标", {"a": 1})
