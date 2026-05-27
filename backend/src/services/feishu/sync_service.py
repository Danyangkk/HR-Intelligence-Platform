from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.models import DataRecord, FeishuSync, Template
from src.services.feishu.mappings import get_sync_config
from src.services.records import compute_uk_hash
from src.services.source import source_of


def run_feishu_sync(l3_id: str) -> dict[str, int | str | bool | None]:
    if source_of(l3_id) != "feishu":
        raise ValueError(f"{l3_id} 不是飞书同步表")

    config = get_sync_config(l3_id)
    if not config:
        raise ValueError(f"尚未实现 {l3_id} 的飞书同步")

    settings = get_settings()
    engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        return _sync_in_session(session, l3_id, config)


def _sync_in_session(session: Session, l3_id: str, config) -> dict[str, int | str | bool | None]:
    sync = session.get(FeishuSync, l3_id)
    if not sync:
        sync = FeishuSync(l3_id=l3_id, status="syncing")
        session.add(sync)
        session.commit()

    tpl = session.get(Template, l3_id)
    if not tpl:
        _mark_error(session, sync, f"模板不存在: {l3_id}")
        raise ValueError(f"模板不存在: {l3_id}")

    try:
        result = config.fetch(get_settings())
        inserted = 0
        updated = 0
        now = datetime.utcnow()

        for payload in result.rows:
            uk_hash = compute_uk_hash(tpl.unique_key, payload)
            existing = session.scalar(
                select(DataRecord).where(DataRecord.l3_id == l3_id, DataRecord.uk_hash == uk_hash)
            )
            if existing:
                existing.payload = payload
                existing.updated_at = now
                updated += 1
            else:
                session.add(
                    DataRecord(
                        l3_id=l3_id,
                        payload=payload,
                        uk_hash=uk_hash,
                        source="feishu",
                    )
                )
                inserted += 1

        sync.status = "idle"
        sync.last_sync_at = now
        sync.next_sync_at = now + timedelta(hours=1)
        sync.error_msg = result.message if result.demo_mode else None
        session.commit()
        return {
            "l3_id": l3_id,
            "inserted": inserted,
            "updated": updated,
            "demo_mode": result.demo_mode,
            "message": result.message,
        }
    except Exception as exc:
        session.rollback()
        sync = session.get(FeishuSync, l3_id)
        if sync:
            _mark_error(session, sync, str(exc))
        raise


def _mark_error(session: Session, sync: FeishuSync, message: str) -> None:
    sync.status = "error"
    sync.error_msg = message[:500]
    session.commit()
