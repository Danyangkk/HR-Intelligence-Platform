from __future__ import annotations

from src.services.feishu.sync_service import run_feishu_sync
from src.workers.celery_app import celery_app


@celery_app.task(name="feishu.sync_l3")
def sync_feishu_l3_task(l3_id: str) -> dict:
    return run_feishu_sync(l3_id)
