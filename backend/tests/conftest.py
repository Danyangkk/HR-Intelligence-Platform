"""Shared pytest fixtures for backend offline gate."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_ROOT_ENV = _BACKEND_DIR.parent / ".env"
_BACKEND_ENV = _BACKEND_DIR / ".env"


def _localhost_env_text(text: str) -> str:
    if _ROOT_ENV.exists() and "@localhost:" in _ROOT_ENV.read_text(encoding="utf-8"):
        return _ROOT_ENV.read_text(encoding="utf-8")
    return (
        text.replace("@postgres:", "@localhost:")
        .replace("redis://redis", "redis://localhost")
        .replace("MINIO_ENDPOINT=minio:9000", "MINIO_ENDPOINT=localhost:9000")
    )


def _prepare_backend_env_for_pytest() -> None:
    """Host pytest uses localhost — reload settings in-memory only; never overwrite backend/.env."""
    if not _BACKEND_ENV.exists():
        return
    text = _BACKEND_ENV.read_text(encoding="utf-8")
    if "@postgres:" not in text and "redis://redis" not in text and "minio:9000" not in text:
        return
    from src.core.config import AppSettings, _manager, DotEnvConfigLoader

    loader = DotEnvConfigLoader()
    patched = _localhost_env_text(text)
    tmp = _BACKEND_DIR / ".env.pytest"
    tmp.write_text(patched, encoding="utf-8")
    try:
        _manager.load(AppSettings, tmp, use_env=False)
    finally:
        tmp.unlink(missing_ok=True)


_prepare_backend_env_for_pytest()

from src.db.session import engine  # noqa: E402  — after env fix


@pytest.fixture(autouse=True)
def force_offline_agent_paths(monkeypatch):
    """Offline gate: planner rules fallback + no live LLM in agent nodes."""
    monkeypatch.setattr("src.agent.planner_llm.plan_with_llm", lambda *a, **k: None)
    monkeypatch.setattr("src.agent.llm_runner.agent_llm_enabled", lambda: False)


@pytest.fixture(autouse=True)
def agent_tool_payroll_confirm_for_biz(monkeypatch):
    """Tools call query_structured without payroll_confirmed; biz_super_admin org-cost reads need it."""
    from src.services import rbac
    import src.services.agent.structured_query as structured_query

    _orig_mask = rbac.mask_items

    def _mask_items(
        role: str,
        l3_id: str,
        items: list,
        *,
        payroll_access: bool = False,
        payroll_confirmed: bool = False,
    ):
        if rbac.is_payroll_l3(l3_id) and rbac.normalize_role(role) == rbac.BIZ_SUPER_ADMIN:
            payroll_confirmed = True
        return _orig_mask(
            role,
            l3_id,
            items,
            payroll_access=payroll_access,
            payroll_confirmed=payroll_confirmed,
        )

    monkeypatch.setattr(structured_query, "mask_items", _mask_items)


@pytest_asyncio.fixture(autouse=True)
async def reset_async_engine():
    """Dispose pooled asyncpg connections each test to avoid loop binding errors."""
    await engine.dispose()
    yield
    await engine.dispose()
