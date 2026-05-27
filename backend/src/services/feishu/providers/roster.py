from __future__ import annotations

from typing import Any

from src.core.config import AppSettings
from src.seed.mock_data import MOCK_RECORDS
from src.services.feishu.bitable import FetchResult, fetch_bitable_records, normalize_date
from src.services.feishu.client import FeishuClient

ROSTER_COLUMNS = [
    "姓名",
    "手机号码",
    "工号",
    "人员类型",
    "事业部",
    "部门",
    "职务",
    "序列",
    "直属上级",
    "虚线上级",
    "工作地点",
    "公司",
    "入职日期",
]


def fetch_roster_records(settings: AppSettings) -> FetchResult:
    app_token = settings.feishu_bitable_app_token.strip()
    table_id = settings.feishu_bitable_roster_table_id.strip()
    if app_token and table_id:
        client = FeishuClient(settings)
        rows = fetch_bitable_records(
            client,
            app_token,
            table_id,
            ROSTER_COLUMNS,
            normalize=_normalize_roster_payload,
        )
        return FetchResult(rows=rows, demo_mode=False)

    if settings.feishu_sync_demo_fallback:
        rows = [dict(row) for row in MOCK_RECORDS.get("l3-2-1-4", [])]
        return FetchResult(
            rows=rows,
            demo_mode=True,
            message="未配置 FEISHU_BITABLE_ROSTER_TABLE_ID，已同步演示数据",
        )

    raise ValueError("未配置飞书花名册 Bitable，且演示回退已关闭")


def _normalize_roster_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload["入职日期"] = normalize_date(payload.get("入职日期"))
    phone = payload.get("手机号码")
    if phone not in (None, ""):
        payload["手机号码"] = str(phone).replace(" ", "")
    return payload
