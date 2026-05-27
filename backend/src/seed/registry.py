"""Load category tree and templates extracted from frontend SSOT."""

from __future__ import annotations

import json
from pathlib import Path

GENERATED = Path(__file__).resolve().parent / "generated"


def load_categories() -> list[dict]:
    return json.loads(GENERATED.joinpath("categories.json").read_text(encoding="utf-8"))


def load_templates() -> dict[str, dict]:
    return json.loads(GENERATED.joinpath("templates.json").read_text(encoding="utf-8"))
