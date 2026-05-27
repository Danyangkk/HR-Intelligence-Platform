from __future__ import annotations

import pytest

from src.seed.mock_data import MOCK_RECORDS
from src.seed.mock_records import patch_mock_records
from src.db.session import AsyncSessionLocal
from src.models import DataRecord, Template
from src.services.records import compute_uk_hash
from sqlalchemy import select


@pytest.mark.asyncio
async def test_patch_mock_records_adds_missing_bu_field():
    async with AsyncSessionLocal() as db:
        l3_id = "l3-2-5-1"
        tpl = await db.get(Template, l3_id)
        assert tpl is not None
        payload = dict(MOCK_RECORDS[l3_id][0])
        payload.pop("事业部", None)
        uk_hash = compute_uk_hash(tpl.unique_key, payload)
        existing = await db.scalar(
            select(DataRecord.id).where(DataRecord.l3_id == l3_id, DataRecord.uk_hash == uk_hash)
        )
        if not existing:
            db.add(
                DataRecord(
                    l3_id=l3_id,
                    payload=payload,
                    uk_hash=uk_hash,
                    source="import",
                )
            )
            await db.commit()

        updated = await patch_mock_records(db)
        await db.commit()

        rec = await db.scalar(
            select(DataRecord).where(DataRecord.l3_id == l3_id, DataRecord.uk_hash == uk_hash)
        )
        assert rec is not None
        assert rec.payload.get("事业部") == "杭抖部门"
        assert updated >= 0
