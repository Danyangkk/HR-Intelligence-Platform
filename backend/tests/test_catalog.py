"""Tests for L3 catalog (PR1)."""

from __future__ import annotations

import json
from pathlib import Path

from src.agent.catalog import (
    catalog_prompt_block,
    is_document_l3,
    is_structured_l3,
    load_l3_catalog,
    valid_l3_ids,
)

SEED_DIR = Path(__file__).resolve().parent.parent / "src" / "seed" / "generated"


def _load_categories_json_l3_ids() -> set[str]:
    categories = json.loads(SEED_DIR.joinpath("categories.json").read_text("utf-8"))
    ids = set()
    for l1 in categories:
        for l2 in l1.get("children", []):
            for l3 in l2.get("children", []):
                ids.add(l3["id"])
    return ids


def test_catalog_loads_84_items():
    catalog = load_l3_catalog()
    assert len(catalog) == 84


def test_every_item_has_description():
    for item in load_l3_catalog():
        assert item["description"], f"{item['id']} missing description"


def test_source_classification_correct():
    for item in load_l3_catalog():
        if item["id"].startswith("l3-1-"):
            assert item["source"] == "document", f"{item['id']} should be document"
        else:
            assert item["source"] == "structured", f"{item['id']} should be structured"


def test_valid_l3_ids_matches_categories_json():
    expected = _load_categories_json_l3_ids()
    actual = valid_l3_ids()
    assert actual == expected


def test_is_document_l3():
    assert is_document_l3("l3-1-1-1") is True
    assert is_document_l3("l3-1-3-3") is True
    assert is_document_l3("l3-2-1-1") is False
    assert is_document_l3("l3-4-1-1") is False


def test_is_structured_l3():
    assert is_structured_l3("l3-2-1-4") is True
    assert is_structured_l3("l3-4-1-1") is True
    assert is_structured_l3("l3-1-1-1") is False


def test_catalog_prompt_block_not_empty():
    block = catalog_prompt_block()
    assert len(block) > 1000
    assert "l3-1-1-1" in block
    assert "l3-4-1-1" in block
    assert "文档(RAG)" in block
    assert "结构化" in block


def test_phantom_id_rejected():
    assert "l3-9-9-9" not in valid_l3_ids()
