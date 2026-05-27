from __future__ import annotations

import pytest

from src.db.session import engine


@pytest.fixture(autouse=True)
async def reset_async_engine():
    """Dispose pooled asyncpg connections so each test gets a fresh loop binding."""
    yield
    await engine.dispose()
