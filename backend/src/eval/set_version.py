"""Eval set / pipeline version anchors for gate optimistic locking."""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.eval.loader import EVAL_SET_PATH

PIPELINE_VERSION = "agent-v1"


def get_eval_set_version(path: Path | None = None) -> str:
    p = path or EVAL_SET_PATH
    digest = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    return f"eval-set-{digest}"


def get_pipeline_version() -> str:
    return PIPELINE_VERSION
