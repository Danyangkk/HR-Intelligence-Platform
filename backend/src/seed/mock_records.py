"""Insert mock business records into data_record."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import DataRecord, FeishuSync, Template
from src.seed.mock_data import MOCK_RECORDS
from src.services.records import compute_uk_hash
from src.services.source import source_of


async def seed_mock_records(session: AsyncSession, force: bool = False) -> int:
    existing = await session.scalar(select(DataRecord.id).limit(1))
    if existing and not force:
        return 0

    if force:
        for l3_id in MOCK_RECORDS:
            await session.execute(
                DataRecord.__table__.delete().where(DataRecord.l3_id == l3_id)
            )

    inserted = 0
    now = datetime.utcnow()
    for l3_id, rows in MOCK_RECORDS.items():
        tpl = await session.get(Template, l3_id)
        if not tpl:
            continue
        src = source_of(l3_id)
        for payload in rows:
            uk_hash = compute_uk_hash(tpl.unique_key, payload)
            dup = await session.scalar(
                select(DataRecord.id).where(DataRecord.l3_id == l3_id, DataRecord.uk_hash == uk_hash)
            )
            if dup:
                continue
            session.add(
                DataRecord(
                    l3_id=l3_id,
                    payload=payload,
                    uk_hash=uk_hash,
                    source=src,
                )
            )
            inserted += 1

        if src == "feishu":
            sync = await session.get(FeishuSync, l3_id)
            if sync:
                sync.last_sync_at = now - timedelta(hours=2)
                sync.next_sync_at = now + timedelta(hours=1)
                sync.status = "idle"
                sync.error_msg = None

    return inserted


async def patch_mock_records(session: AsyncSession) -> int:
    """Merge missing fields from MOCK_RECORDS into existing rows (idempotent upsert)."""
    updated = 0
    for l3_id, rows in MOCK_RECORDS.items():
        tpl = await session.get(Template, l3_id)
        if not tpl:
            continue
        for payload in rows:
            uk_hash = compute_uk_hash(tpl.unique_key, payload)
            rec = await session.scalar(
                select(DataRecord).where(DataRecord.l3_id == l3_id, DataRecord.uk_hash == uk_hash)
            )
            if not rec:
                continue
            merged = dict(rec.payload or {})
            changed = False
            for key, value in payload.items():
                if value is None or value == "":
                    continue
                if merged.get(key) in (None, ""):
                    merged[key] = value
                    changed = True
            if changed:
                rec.payload = merged
                updated += 1
    return updated
