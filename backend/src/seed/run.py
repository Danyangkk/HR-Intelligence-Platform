"""Seed categories, templates, feishu_sync rows, and MVP test users."""

from __future__ import annotations

import asyncio
import json

from passlib.context import CryptContext
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import AsyncSessionLocal, engine
from src.models import Category, DataRecord, FeishuSync, Template, User
from src.seed.mock_records import patch_mock_records, seed_mock_records
from src.seed.registry import load_categories, load_templates
from src.services.improvement_tickets import seed_demo_tickets, seed_demo_users
from src.services.source import source_of

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_USERS = [
    ("hr_admin", "admin123", "hr_admin", "HR 管理员"),
    ("viewer", "viewer123", "viewer", "只读用户"),
    ("agent", "agent123", "agent", "智能体服务账号"),
]

TEMPLATE_ALIASES = {
    "l3-6-1-2": "l3-6-1-1",
    "l3-6-1-3": "l3-6-1-1",
    "l3-5-2-2": "l3-5-2-1",
    "l3-5-2-3": "l3-5-2-1",
}


def _expand_templates(raw: dict[str, dict]) -> dict[str, dict]:
    templates = dict(raw)
    for alias, base in TEMPLATE_ALIASES.items():
        if base in templates and alias not in templates:
            templates[alias] = json.loads(json.dumps(templates[base]))
    return templates


async def sync_templates(session: AsyncSession) -> int:
    """Keep template metadata in DB aligned with generated JSON (idempotent)."""
    templates = _expand_templates(load_templates())
    changed = 0
    for l3_id, tpl in templates.items():
        row = await session.get(Template, l3_id)
        if not row:
            continue
        expected_filters = tpl.get("filters") or []
        expected_columns = tpl["columns"]
        expected_unique_key = tpl.get("unique_key") or [expected_columns[0]]
        if (
            row.filters != expected_filters
            or row.columns != expected_columns
            or row.unique_key != expected_unique_key
        ):
            row.filters = expected_filters
            row.columns = expected_columns
            row.unique_key = expected_unique_key
            changed += 1
    return changed


async def seed_all(force: bool = False) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    async with AsyncSessionLocal() as session:
        synced = await sync_templates(session)
        if synced:
            await session.commit()
            print(f"seed: synced template filters for {synced} tables")

        existing_cat = await session.scalar(select(Category.id).limit(1))
        existing_data = await session.scalar(select(DataRecord.id).limit(1))

        if existing_cat and not force:
            patched = await patch_mock_records(session)
            if patched:
                await session.commit()
                print(f"seed: patched {patched} mock record(s) with missing fields")
            if not existing_data:
                mock_count = await seed_mock_records(session, force=False)
                await session.commit()
                print(f"seed: mock_records={mock_count} (categories already present)")
            else:
                print("seed: already present, skip (use force=True to reseed)")
            return

        if force:
            await session.execute(
                text("TRUNCATE category, template, feishu_sync, users RESTART IDENTITY CASCADE")
            )
            await session.commit()

        sort_l1 = 0
        for l1 in load_categories():
            sort_l1 += 1
            session.add(
                Category(
                    id=l1["id"],
                    level=1,
                    parent_id=None,
                    name=l1["name"],
                    source=None,
                    sort=sort_l1,
                )
            )
            sort_l2 = 0
            for l2 in l1.get("children", []):
                sort_l2 += 1
                session.add(
                    Category(
                        id=l2["id"],
                        level=2,
                        parent_id=l1["id"],
                        name=l2["name"],
                        source=None,
                        sort=sort_l2,
                    )
                )
                sort_l3 = 0
                for l3 in l2.get("children", []):
                    sort_l3 += 1
                    l3_id = l3["id"]
                    session.add(
                        Category(
                            id=l3_id,
                            level=3,
                            parent_id=l2["id"],
                            name=l3["name"],
                            source=source_of(l3_id),
                            sort=sort_l3,
                        )
                    )

        templates = _expand_templates(load_templates())
        for l3_id, tpl in templates.items():
            session.add(
                Template(
                    l3_id=l3_id,
                    columns=tpl["columns"],
                    filters=tpl.get("filters") or [],
                    unique_key=tpl.get("unique_key") or [tpl["columns"][0]],
                )
            )

        for l3_id in templates:
            if source_of(l3_id) == "feishu":
                session.add(FeishuSync(l3_id=l3_id, status="idle"))

        for username, password, role, display_name in TEST_USERS:
            exists = await session.scalar(select(User.id).where(User.username == username))
            if exists:
                continue
            session.add(
                User(
                    username=username,
                    password_hash=pwd_context.hash(password),
                    role=role,
                    display_name=display_name,
                )
            )

        await seed_demo_users(session, pwd_context.hash)
        await seed_demo_tickets(session)

        await session.commit()
        mock_count = await seed_mock_records(session, force=force)
        if mock_count:
            await session.commit()

        print(
            f"seed: done — l3=84 templates={len(templates)} "
            f"feishu_sync={sum(1 for i in templates if source_of(i) == 'feishu')} "
            f"users={len(TEST_USERS)} mock_records={mock_count or 'skipped'}"
        )


async def _main() -> None:
    await seed_all(force=False)


if __name__ == "__main__":
    asyncio.run(_main())
