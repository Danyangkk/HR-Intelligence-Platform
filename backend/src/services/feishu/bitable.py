from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from src.services.feishu.client import FeishuClient

NormalizeFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class FetchResult:
    rows: list[dict[str, Any]]
    demo_mode: bool = False
    message: str | None = None


def fetch_bitable_records(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    columns: list[str],
    *,
    normalize: NormalizeFn | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params: dict[str, Any] = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        data = client.get(
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            params=params,
        )
        for item in data.get("items") or []:
            fields = item.get("fields") or {}
            payload = map_bitable_fields(fields, columns)
            if normalize:
                payload = normalize(payload)
            rows.append(payload)
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
        if not page_token:
            break
    return rows


def map_bitable_fields(fields: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    return {column: normalize_value(resolve_field(fields, column)) for column in columns}


def resolve_field(fields: dict[str, Any], column: str) -> Any:
    if column in fields:
        return fields[column]
    for key, value in fields.items():
        base = key.strip()
        if base == column or base.startswith(f"{column} ") or base.startswith(column):
            return value
    return None


def normalize_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [normalize_value(item) for item in value]
        return "、".join(str(part) for part in parts if part not in ("", None))
    if isinstance(value, dict):
        if "text" in value:
            return str(value.get("text") or "").strip()
        if "name" in value:
            return str(value.get("name") or value.get("en_name") or "").strip()
        if "value" in value:
            return normalize_value(value.get("value"))
        if "full_address" in value:
            return str(value.get("full_address") or "").strip()
    return str(value).strip()


def normalize_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    text = str(value).strip()
    if len(text) >= 10 and text[4] in "-/":
        return text[:10].replace("/", "-")
    return text
