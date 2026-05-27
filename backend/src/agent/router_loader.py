"""Load ROUTER.md — single source of truth for intent routing."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_ROUTER_PATH = Path(__file__).resolve().parent / "ROUTER.md"


@lru_cache(maxsize=1)
def load_router() -> str:
    """Return full ROUTER.md text for Planner injection."""
    if not _ROUTER_PATH.exists():
        return ""
    return _ROUTER_PATH.read_text(encoding="utf-8").strip()


def inject_router(template: str, *, router: str | None = None) -> str:
    """Replace ``{{router}}`` placeholder with ROUTER body."""
    body = router if router is not None else load_router()
    return template.replace("{{router}}", body)
