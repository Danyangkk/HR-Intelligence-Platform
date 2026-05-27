from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.core.config import AppSettings
from src.services.feishu.providers.leave import fetch_leave_records
from src.services.feishu.providers.roster import fetch_roster_records
from src.services.feishu.table_configs import FEISHU_TABLE_CONFIGS, make_fetch_fn

FetchFn = Callable[[AppSettings], Any]


@dataclass(frozen=True)
class L3SyncConfig:
    l3_id: str
    fetch: FetchFn


# 11 张飞书同步表（D11）：档案/任职/花名册 + 考勤7张 + 异动
SYNC_REGISTRY: dict[str, L3SyncConfig] = {
    l3_id: L3SyncConfig(l3_id=l3_id, fetch=make_fetch_fn(l3_id))
    for l3_id in FEISHU_TABLE_CONFIGS
}
# 保留 leave/roster 专用 normalize（覆盖 generic）
SYNC_REGISTRY["l3-2-2-1"] = L3SyncConfig(l3_id="l3-2-2-1", fetch=fetch_leave_records)
SYNC_REGISTRY["l3-2-1-4"] = L3SyncConfig(l3_id="l3-2-1-4", fetch=fetch_roster_records)


def get_sync_config(l3_id: str) -> L3SyncConfig | None:
    return SYNC_REGISTRY.get(l3_id)


def list_feishu_sync_l3_ids() -> list[str]:
    return sorted(SYNC_REGISTRY.keys())
