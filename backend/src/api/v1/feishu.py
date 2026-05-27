from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.response import fail, ok
from src.core.config import get_settings
from src.db.session import get_db
from src.models import Category, FeishuSync
from src.api.deps import CurrentUser, get_optional_user, require_sync
from src.services.audit import write_audit
from src.services.feishu.config_status import feishu_table_config_status
from src.services.feishu.mappings import get_sync_config, list_feishu_sync_l3_ids
from src.services.source import source_of
from src.workers.feishu_tasks import sync_feishu_l3_task

router = APIRouter(prefix="/feishu", tags=["feishu"])


def _is_feishu_l3(cat: Category | None, l3_id: str) -> bool:
    if not cat:
        return False
    src = cat.source or source_of(l3_id)
    return src == "feishu"


async def _get_or_create_sync(db: AsyncSession, l3_id: str) -> FeishuSync:
    sync = await db.get(FeishuSync, l3_id)
    if sync:
        return sync
    sync = FeishuSync(l3_id=l3_id, status="idle")
    db.add(sync)
    await db.commit()
    await db.refresh(sync)
    return sync


@router.get("/config/status")
async def feishu_config_status() -> dict:
    return ok(feishu_table_config_status())


@router.post("/sync-all")
async def feishu_sync_all(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict:
    require_sync(user)
    triggered: list[str] = []
    skipped: list[str] = []
    for l3_id in list_feishu_sync_l3_ids():
        cat = await db.get(Category, l3_id)
        if not _is_feishu_l3(cat, l3_id) or not get_sync_config(l3_id):
            skipped.append(l3_id)
            continue
        sync = await _get_or_create_sync(db, l3_id)
        if sync.status == "syncing":
            skipped.append(l3_id)
            continue
        sync.status = "syncing"
        sync.error_msg = None
        sync_feishu_l3_task.delay(l3_id)
        triggered.append(l3_id)
    await db.commit()
    if triggered:
        await write_audit(db, actor=user.username, action="feishu.sync_all", l3_id=",".join(triggered))
    return ok({"triggered": triggered, "skipped": skipped, "count": len(triggered)})


@router.post("/webhook")
async def feishu_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """飞书事件回调 — 审批/异动等触发增量 sync（§3.7）"""
    settings = get_settings()
    body = await request.json()
    if settings.feishu_verification_token:
        token = body.get("token") or (body.get("header") or {}).get("token")
        if token != settings.feishu_verification_token:
            return fail(403, "invalid verification token")

    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    event = body.get("event") or {}
    l3_candidates = list_feishu_sync_l3_ids()
    triggered: list[str] = []
    for l3_id in l3_candidates[:3]:
        sync = await _get_or_create_sync(db, l3_id)
        if sync.status != "syncing":
            sync.status = "syncing"
            sync_feishu_l3_task.delay(l3_id)
            triggered.append(l3_id)
    await db.commit()
    return ok({"status": "accepted", "triggered": triggered, "event_type": event.get("type") or body.get("type")})


@router.get("/{l3_id}/status")
async def feishu_status(l3_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    cat = await db.get(Category, l3_id)
    if not _is_feishu_l3(cat, l3_id):
        return ok({"l3_id": l3_id, "status": "not_feishu", "last_sync_at": None, "next_sync_at": None})

    sync = await _get_or_create_sync(db, l3_id)
    return ok(
        {
            "l3_id": l3_id,
            "status": sync.status,
            "last_sync_at": sync.last_sync_at.isoformat() if sync.last_sync_at else None,
            "next_sync_at": sync.next_sync_at.isoformat() if sync.next_sync_at else None,
            "error_msg": sync.error_msg,
        }
    )


@router.post("/{l3_id}/sync")
async def feishu_sync(
    l3_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_optional_user),
) -> dict:
    require_sync(user)
    cat = await db.get(Category, l3_id)
    if not _is_feishu_l3(cat, l3_id):
        return fail(400, "该分类不是飞书同步表")

    if not get_sync_config(l3_id):
        return fail(400, f"尚未实现 {l3_id} 的飞书同步")

    sync = await _get_or_create_sync(db, l3_id)
    if sync.status == "syncing":
        return ok({"l3_id": l3_id, "status": "syncing", "message": "同步任务进行中"})

    sync.status = "syncing"
    sync.error_msg = None
    await db.commit()

    sync_feishu_l3_task.delay(l3_id)
    await write_audit(
        db,
        actor=None if user.username == "anonymous" else user.username,
        action="feishu.sync",
        l3_id=l3_id,
    )
    return ok({"l3_id": l3_id, "status": "syncing", "message": "已触发飞书同步"})
