from __future__ import annotations

from celery.schedules import crontab

from src.services.feishu.mappings import list_feishu_sync_l3_ids
from src.workers.celery_app import celery_app

# 考勤类 hourly；花名册/异动 daily（§3.7）
_ATTENDANCE_L3 = [
    "l3-2-2-1",
    "l3-2-2-2",
    "l3-2-2-3",
    "l3-2-2-4",
    "l3-2-2-5",
    "l3-2-2-6",
    "l3-2-2-7",
]
_DAILY_L3 = ["l3-2-1-1", "l3-2-1-2", "l3-2-1-4", "l3-2-3-1"]

_beat_schedule: dict = {}
for l3_id in _ATTENDANCE_L3:
    if l3_id in list_feishu_sync_l3_ids():
        _beat_schedule[f"feishu-hourly-{l3_id}"] = {
            "task": "feishu.sync_l3",
            "schedule": crontab(minute=0),
            "args": (l3_id,),
        }
for l3_id in _DAILY_L3:
    if l3_id in list_feishu_sync_l3_ids():
        _beat_schedule[f"feishu-daily-{l3_id}"] = {
            "task": "feishu.sync_l3",
            "schedule": crontab(hour=2, minute=0),
            "args": (l3_id,),
        }

celery_app.conf.beat_schedule = _beat_schedule
