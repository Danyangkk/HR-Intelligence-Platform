from __future__ import annotations

from typing import Any

from src.core.config import AppSettings
from src.core.constants import APPROVAL_STATUSES, BU_UNITS
from src.seed.mock_data import MOCK_RECORDS
from src.services.feishu.bitable import FetchResult, fetch_bitable_records, normalize_date
from src.services.feishu.client import FeishuClient

LEAVE_COLUMNS = [
    "工号",
    "姓名",
    "事业部",
    "部门",
    "请假类型",
    "开始日期",
    "结束日期",
    "请假天数",
    "审批状态",
    "审批人",
]

APPROVAL_STATUS_MAP = {
    "pending": "待批准",
    "approving": "审批中",
    "approved": "已批准",
    "rejected": "已拒绝",
    "canceled": "已撤回",
    "cancelled": "已撤回",
    "待审批": "待批准",
    "待批准": "待批准",
    "审批中": "审批中",
    "已通过": "已批准",
    "已审批": "已批准",
    "已批准": "已批准",
    "已拒绝": "已拒绝",
    "已撤回": "已撤回",
}


def fetch_leave_records(settings: AppSettings) -> FetchResult:
    app_token = settings.feishu_bitable_app_token.strip()
    table_id = settings.feishu_bitable_leave_table_id.strip()
    if app_token and table_id:
        client = FeishuClient(settings)
        rows = fetch_bitable_records(
            client,
            app_token,
            table_id,
            LEAVE_COLUMNS,
            normalize=_normalize_leave_payload,
        )
        return FetchResult(rows=rows, demo_mode=False)

    if settings.feishu_sync_demo_fallback:
        rows = [dict(row) for row in MOCK_RECORDS.get("l3-2-2-1", [])]
        return FetchResult(
            rows=rows,
            demo_mode=True,
            message="未配置 FEISHU_BITABLE_LEAVE_TABLE_ID，已同步演示数据",
        )

    raise ValueError("未配置飞书请假 Bitable，且演示回退已关闭")


def _normalize_leave_payload(payload: dict[str, Any]) -> dict[str, Any]:
    bu = str(payload.get("事业部") or "").strip()
    if bu and bu not in BU_UNITS:
        for candidate in BU_UNITS:
            if candidate.startswith(bu) or bu in candidate or candidate.replace("部门", "") == bu:
                bu = candidate
                break
        else:
            bu_map = {"杭综": "杭综部门", "杭抖": "杭抖部门", "职能": "职能部门"}
            bu = bu_map.get(bu, bu)
    if bu:
        payload["事业部"] = bu

    status = str(payload.get("审批状态") or "").strip()
    if status:
        mapped = APPROVAL_STATUS_MAP.get(status.lower(), APPROVAL_STATUS_MAP.get(status, status))
        if mapped in APPROVAL_STATUSES:
            payload["审批状态"] = mapped

    for date_field in ("开始日期", "结束日期"):
        payload[date_field] = normalize_date(payload.get(date_field))

    days = payload.get("请假天数")
    if days not in (None, ""):
        try:
            payload["请假天数"] = int(float(days))
        except (TypeError, ValueError):
            payload["请假天数"] = days

    return payload
