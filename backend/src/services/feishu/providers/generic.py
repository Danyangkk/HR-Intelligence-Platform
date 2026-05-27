"""Generic Feishu Bitable fetch by l3_id table config."""

from __future__ import annotations

from typing import Any

from src.core.config import AppSettings
from src.seed.mock_data import MOCK_RECORDS
from src.services.feishu.bitable import FetchResult, fetch_bitable_records, normalize_date
from src.services.feishu.client import FeishuClient
from src.services.feishu.table_configs import FEISHU_TABLE_CONFIGS, resolve_table_id


def fetch_configured_table(settings: AppSettings, l3_id: str) -> FetchResult:
    cfg = FEISHU_TABLE_CONFIGS.get(l3_id)
    if not cfg:
        raise ValueError(f"未注册的飞书表：{l3_id}")

    app_token = settings.feishu_bitable_app_token.strip()
    table_id = resolve_table_id(settings, l3_id)
    if app_token and table_id:
        client = FeishuClient(settings)
        rows = fetch_bitable_records(
            client,
            app_token,
            table_id,
            list(cfg.columns),
            normalize=_make_normalizer(cfg.date_fields),
        )
        return FetchResult(rows=rows, demo_mode=False)

    if settings.feishu_sync_demo_fallback:
        rows = [dict(row) for row in MOCK_RECORDS.get(l3_id, [])]
        return FetchResult(
            rows=rows,
            demo_mode=True,
            message=f"未配置 {cfg.settings_attr}，已同步演示数据",
        )

    raise ValueError(f"未配置飞书 {l3_id} Bitable，且演示回退已关闭")


def _make_normalizer(date_fields: tuple[str, ...]):
    def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
        for field in date_fields:
            if field in payload:
                payload[field] = normalize_date(payload.get(field))
        return payload

    return _normalize if date_fields else None
