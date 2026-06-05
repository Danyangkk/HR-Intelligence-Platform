"""L3 catalog — single source of truth for Planner's table knowledge."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SEED_DIR = Path(__file__).resolve().parent.parent / "seed" / "generated"


@lru_cache(maxsize=1)
def load_l3_catalog() -> list[dict]:
    """Build catalog from categories.json + templates.json.

    Each item: {id, path, source, description, fields}
    """
    import json

    categories = json.loads(_SEED_DIR.joinpath("categories.json").read_text("utf-8"))
    templates = json.loads(_SEED_DIR.joinpath("templates.json").read_text("utf-8"))

    catalog: list[dict] = []
    for l1 in categories:
        for l2 in l1.get("children", []):
            for l3 in l2.get("children", []):
                l3_id = l3["id"]
                path = f"{l1['name']}/{l2['name']}/{l3['name']}"
                source = _classify_source(l3_id)
                fields = templates.get(l3_id, {}).get("columns", [])[:8]
                catalog.append(
                    {
                        "id": l3_id,
                        "path": path,
                        "source": source,
                        "description": l3.get("description") or "",
                        "fields": fields,
                    }
                )
    return catalog


def _classify_source(l3_id: str) -> str:
    """document (RAG) for l1-1 管理制度 subtree; structured for everything else."""
    if l3_id.startswith("l3-1-"):
        return "document"
    return "structured"


@lru_cache(maxsize=1)
def valid_l3_ids() -> frozenset[str]:
    return frozenset(item["id"] for item in load_l3_catalog())


def is_document_l3(l3_id: str) -> bool:
    for item in load_l3_catalog():
        if item["id"] == l3_id:
            return item["source"] == "document"
    return False


def is_structured_l3(l3_id: str) -> bool:
    for item in load_l3_catalog():
        if item["id"] == l3_id:
            return item["source"] == "structured"
    return False


def catalog_prompt_block() -> str:
    """Render compact text block for injection into Planner prompt.

    Format per line:
      l3-id｜一级/二级/三级名｜source_label｜description｜字段:f1,f2,...
    """
    lines: list[str] = []
    for item in load_l3_catalog():
        source_label = "文档(RAG)" if item["source"] == "document" else "结构化"
        parts = [item["id"], item["path"], source_label, item["description"]]
        if item["fields"]:
            parts.append("字段:" + ",".join(item["fields"]))
        lines.append("｜".join(parts))
    return "\n".join(lines)
