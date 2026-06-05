"""Eval run version label — default trigger timestamp or custom tag."""

from __future__ import annotations

from datetime import datetime

# Placeholder names used in early dev / tests — not valid run labels (except pytest).
_GARBAGE_VERSIONS = frozenset({
    "t",
    "dev",
    "test",
    "",
    "base",
    "cur",
    "release-test",
    "release-ok",
})


def get_default_eval_version(now: datetime | None = None) -> str:
    """Default label: MMDD-HHmm at trigger time, e.g. 0605-1138."""
    dt = now or datetime.now()
    return dt.strftime("%m%d-%H%M")


def normalize_eval_version(version: str | None, *, now: datetime | None = None) -> str:
    v = (version or "").strip()
    if not v:
        return get_default_eval_version(now)
    if is_garbage_eval_version(v):
        return get_default_eval_version(now)
    return v[:64]


def is_garbage_eval_version(version: str | None) -> bool:
    v = (version or "").strip()
    if not v or len(v) <= 1:
        return True
    if v.lower() in _GARBAGE_VERSIONS:
        return True
    return False
