"""Released eval baseline pointer (moves forward on ticket release)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import EvalBaseline


async def get_released_baseline_run_id(db: AsyncSession) -> int | None:
    row = await db.get(EvalBaseline, 1)
    if not row:
        return None
    return row.released_baseline_run_id


async def set_released_baseline_run_id(db: AsyncSession, run_id: int | None) -> None:
    row = await db.get(EvalBaseline, 1)
    if not row:
        row = EvalBaseline(id=1, released_baseline_run_id=run_id)
        db.add(row)
    else:
        row.released_baseline_run_id = run_id
    await db.commit()
