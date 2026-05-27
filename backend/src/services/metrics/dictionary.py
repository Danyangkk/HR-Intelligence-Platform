from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_RESOURCES = Path(__file__).resolve().parents[3] / "resources" / "metrics_dictionary.json"


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    name: str
    category: str
    formula: str
    unit: str
    value_type: str
    inputs: tuple[str, ...]
    notes: str
    aliases: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    benchmark: str = ""
    threshold: str = ""
    citation: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "formula": self.formula,
            "unit": self.unit,
            "value_type": self.value_type,
            "inputs": list(self.inputs),
            "notes": self.notes,
        }
        if self.benchmark:
            data["benchmark"] = self.benchmark
        if self.threshold:
            data["threshold"] = self.threshold
        if self.citation:
            data["citation"] = self.citation
        if self.aliases:
            data["aliases"] = list(self.aliases)
        if self.depends_on:
            data["depends_on"] = list(self.depends_on)
        return data


def _parse_metric(raw: dict[str, Any]) -> MetricDefinition:
    return MetricDefinition(
        id=str(raw["id"]),
        name=str(raw["name"]),
        category=str(raw["category"]),
        formula=str(raw["formula"]),
        unit=str(raw.get("unit") or "ratio"),
        value_type=str(raw.get("value_type") or "ratio"),
        inputs=tuple(raw.get("inputs") or []),
        notes=str(raw.get("notes") or ""),
        aliases=tuple(raw.get("aliases") or []),
        depends_on=tuple(raw.get("depends_on") or []),
        benchmark=str(raw.get("benchmark") or ""),
        threshold=str(raw.get("threshold") or ""),
        citation=str(raw.get("citation") or raw.get("formula") or ""),
    )


@lru_cache
def load_metrics() -> tuple[MetricDefinition, ...]:
    if not _RESOURCES.exists():
        raise FileNotFoundError(f"metrics dictionary not found: {_RESOURCES}")
    raw = json.loads(_RESOURCES.read_text(encoding="utf-8"))
    return tuple(_parse_metric(item) for item in raw)


def list_metrics(*, category: str | None = None) -> list[dict[str, Any]]:
    items = load_metrics()
    if category:
        items = [item for item in items if item.category == category]
    return [item.to_dict() for item in items]


def list_categories() -> list[str]:
    return sorted({item.category for item in load_metrics()})


def get_metric(name_or_id: str) -> MetricDefinition | None:
    key = name_or_id.strip()
    if not key:
        return None
    lowered = key.lower()
    for item in load_metrics():
        if item.name == key or item.id == key:
            return item
        if lowered in {alias.lower() for alias in item.aliases}:
            return item
    return None


def get_metric_by_id(metric_id: str) -> MetricDefinition | None:
    for item in load_metrics():
        if item.id == metric_id:
            return item
    return None


def search_metrics(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return list_metrics()
    hits: list[MetricDefinition] = []
    for item in load_metrics():
        haystack = " ".join([item.name, item.formula, item.category, *item.aliases]).lower()
        if q in haystack or q in item.name.lower():
            hits.append(item)
        if len(hits) >= limit:
            break
    return [item.to_dict() for item in hits]
