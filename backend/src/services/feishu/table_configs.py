"""Feishu Bitable table definitions for 11 sync tables (D11)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.core.config import AppSettings


@dataclass(frozen=True)
class FeishuTableConfig:
    l3_id: str
    columns: tuple[str, ...]
    settings_attr: str
    date_fields: tuple[str, ...] = ()


def _table_id(settings: AppSettings, attr: str) -> str:
    return str(getattr(settings, attr, "") or "").strip()


FEISHU_TABLE_CONFIGS: dict[str, FeishuTableConfig] = {
    "l3-2-1-1": FeishuTableConfig(
        l3_id="l3-2-1-1",
        columns=("工号", "姓名", "事业部", "部门", "性别", "身份证号", "出生日期", "学历", "毕业院校", "专业", "联系电话", "婚姻状况"),
        settings_attr="feishu_bitable_profile_table_id",
    ),
    "l3-2-1-2": FeishuTableConfig(
        l3_id="l3-2-1-2",
        columns=("工号", "姓名", "事业部", "部门", "岗位", "职级", "汇报对象", "任职开始日", "任职状态"),
        settings_attr="feishu_bitable_position_table_id",
        date_fields=("任职开始日",),
    ),
    "l3-2-1-4": FeishuTableConfig(
        l3_id="l3-2-1-4",
        columns=("姓名", "手机号码", "工号", "人员类型", "事业部", "部门", "职务", "序列", "直属上级", "虚线上级", "工作地点", "公司", "入职日期"),
        settings_attr="feishu_bitable_roster_table_id",
        date_fields=("入职日期",),
    ),
    "l3-2-2-1": FeishuTableConfig(
        l3_id="l3-2-2-1",
        columns=("工号", "姓名", "事业部", "部门", "请假类型", "开始日期", "结束日期", "请假天数", "审批状态", "审批人"),
        settings_attr="feishu_bitable_leave_table_id",
        date_fields=("开始日期", "结束日期"),
    ),
    "l3-2-2-2": FeishuTableConfig(
        l3_id="l3-2-2-2",
        columns=("工号", "姓名", "事业部", "部门", "出差目的地", "出差事由", "开始日期", "结束日期", "出差天数", "审批状态"),
        settings_attr="feishu_bitable_travel_table_id",
        date_fields=("开始日期", "结束日期"),
    ),
    "l3-2-2-3": FeishuTableConfig(
        l3_id="l3-2-2-3",
        columns=("工号", "姓名", "事业部", "部门", "外出事由", "外出时间", "返回时间", "时长(小时)"),
        settings_attr="feishu_bitable_outgoing_table_id",
        date_fields=("外出时间", "返回时间"),
    ),
    "l3-2-2-4": FeishuTableConfig(
        l3_id="l3-2-2-4",
        columns=("工号", "姓名", "事业部", "部门", "加班日期", "开始时间", "结束时间", "加班时长", "加班类型", "审批状态"),
        settings_attr="feishu_bitable_overtime_table_id",
        date_fields=("加班日期",),
    ),
    "l3-2-2-5": FeishuTableConfig(
        l3_id="l3-2-2-5",
        columns=("工号", "姓名", "事业部", "部门", "打卡日期", "上班打卡", "下班打卡", "工作时长", "异常类型"),
        settings_attr="feishu_bitable_access_attendance_table_id",
        date_fields=("打卡日期",),
    ),
    "l3-2-2-6": FeishuTableConfig(
        l3_id="l3-2-2-6",
        columns=("工号", "姓名", "事业部", "部门", "日期", "首次打卡", "末次打卡", "出勤状态", "迟到分钟", "早退分钟"),
        settings_attr="feishu_bitable_feishu_attendance_table_id",
        date_fields=("日期",),
    ),
    "l3-2-2-7": FeishuTableConfig(
        l3_id="l3-2-2-7",
        columns=("事业部", "部门", "统计月份", "应出勤天数", "实际出勤", "请假天数", "加班时长", "迟到次数", "出勤率"),
        settings_attr="feishu_bitable_attendance_summary_table_id",
    ),
    "l3-2-3-1": FeishuTableConfig(
        l3_id="l3-2-3-1",
        columns=("工号", "姓名", "事业部", "异动类型", "原部门", "新部门", "原职级", "新职级", "生效日期", "异动原因", "审批状态"),
        settings_attr="feishu_bitable_change_table_id",
        date_fields=("生效日期",),
    ),
}


def resolve_table_id(settings: AppSettings, l3_id: str) -> str:
    cfg = FEISHU_TABLE_CONFIGS.get(l3_id)
    if not cfg:
        return ""
    return _table_id(settings, cfg.settings_attr)


def make_fetch_fn(l3_id: str) -> Callable[[AppSettings], Any]:
    from src.services.feishu.providers.generic import fetch_configured_table

    def _fetch(settings: AppSettings):
        return fetch_configured_table(settings, l3_id)

    return _fetch
