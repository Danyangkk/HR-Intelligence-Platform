"""Feishu Bitable configuration status for 11 sync tables."""

from __future__ import annotations

from typing import Any

from src.core.config import AppSettings, get_settings
from src.services.feishu.mappings import list_feishu_sync_l3_ids
from src.services.feishu.table_configs import FEISHU_TABLE_CONFIGS, resolve_table_id


def feishu_table_config_status(settings: AppSettings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    app_token = settings.feishu_bitable_app_token.strip()
    rows: list[dict[str, Any]] = []
    configured = 0
    for l3_id in list_feishu_sync_l3_ids():
        cfg = FEISHU_TABLE_CONFIGS[l3_id]
        table_id = resolve_table_id(settings, l3_id)
        ready = bool(app_token and table_id)
        if ready:
            configured += 1
        rows.append(
            {
                "l3_id": l3_id,
                "settings_attr": cfg.settings_attr,
                "table_id": table_id or None,
                "configured": ready,
                "demo_fallback": settings.feishu_sync_demo_fallback and not ready,
            }
        )
    total = len(rows)
    return {
        "app_token_configured": bool(app_token),
        "total_tables": total,
        "configured_tables": configured,
        "all_configured": configured == total,
        "demo_fallback_enabled": settings.feishu_sync_demo_fallback,
        "tables": rows,
    }
