from celery import Celery

from src.core.config import get_settings

settings = get_settings()

celery_app = Celery("hr_agent", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    imports=("src.workers.feishu_tasks", "src.workers.beat_schedule"),
)
