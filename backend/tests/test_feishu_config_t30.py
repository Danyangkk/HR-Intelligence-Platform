from __future__ import annotations

from src.services.feishu.config_status import feishu_table_config_status
from src.services.feishu.mappings import list_feishu_sync_l3_ids


def test_feishu_config_lists_11_tables():
    status = feishu_table_config_status()
    assert status["total_tables"] == 11
    assert len(status["tables"]) == 11
    assert set(list_feishu_sync_l3_ids()) == {row["l3_id"] for row in status["tables"]}


def test_feishu_config_each_table_has_settings_attr():
    status = feishu_table_config_status()
    for row in status["tables"]:
        assert row["settings_attr"]
        assert row["l3_id"].startswith("l3-")
