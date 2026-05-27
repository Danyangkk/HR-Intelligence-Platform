from __future__ import annotations

from src.services.metrics.dictionary import get_metric, list_categories, load_metrics

# SSOT 附录 D 全表指标名（与 metrics_dictionary.json 对齐）
APPENDIX_D_METRICS = [
    "在职人数",
    "期初在职",
    "期末在职",
    "平均在职人数",
    "入职率",
    "离职率",
    "主动离职率",
    "转正率",
    "试用期流失率",
    "人员稳定率",
    "出勤率",
    "缺勤率",
    "人均加班时长",
    "加班率",
    "请假率",
    "编制达成率",
    "缺编数",
    "超编数",
    "管理幅度",
    "绩效达成率",
    "优秀率",
    "绩效分布偏离",
    "业绩达成率",
    "人力成本合计",
    "人均人力成本",
    "人效(人均营收)",
    "人均利润",
    "薪酬费用率",
    "成本环比",
    "成本同比",
]

APPENDIX_D_CATEGORIES = [
    "人员与流动",
    "考勤与投入",
    "编制与组织",
    "绩效",
    "成本与人效",
]


def test_appendix_d_metric_count():
    assert len(load_metrics()) == len(APPENDIX_D_METRICS)


def test_appendix_d_all_metrics_present():
    missing = [name for name in APPENDIX_D_METRICS if get_metric(name) is None]
    assert not missing, f"missing metrics: {missing}"


def test_appendix_d_categories():
    assert set(list_categories()) == set(APPENDIX_D_CATEGORIES)


def test_turnover_rate_has_citation():
    defn = get_metric("离职率")
    assert defn is not None
    assert defn.citation
    assert "离职" in defn.citation
