from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import BU_UNITS
from src.models import DataRecord, Template
from src.services.records import compute_uk_hash


def validate_headers(template: Template, headers: list[str]) -> dict[str, Any]:
    cols = list(template.columns)
    header_list = [str(h).strip() for h in headers]
    fset = set(header_list)
    tset = set(cols)
    missing = [c for c in cols if c not in fset]
    extras = [h for h in header_list if h not in tset]
    ok = not missing and not extras
    order_diff = ok and any(
        i < len(header_list) and header_list[i] != cols[i] for i in range(len(cols))
    )

    diff: list[dict[str, Any]] = []
    if not ok:
        max_len = max(len(cols), len(header_list))
        for i in range(max_len):
            tc = cols[i] if i < len(cols) else None
            fc = header_list[i] if i < len(header_list) else None
            if tc and fc and tc == fc:
                diff.append({"pos": f"第{i + 1}列", "tpl": tc, "file": fc, "ok": True})
            else:
                msg = "缺少该列" if not fc else "多出的列" if not tc else ("顺序不符" if tc in fset else "名称不符")
                diff.append(
                    {
                        "pos": f"第{i + 1}列" if tc else "额外列",
                        "tpl": tc or "—",
                        "file": fc or "（缺失）",
                        "ok": False,
                        "msg": msg,
                    }
                )

    summary_parts: list[str] = []
    if missing:
        summary_parts.append(f"缺 {len(missing)} 列")
    if extras:
        summary_parts.append(f"多 {len(extras)} 列")
    summary = f"（{'、'.join(summary_parts)}）" if summary_parts else ""

    return {
        "ok": ok,
        "order_diff": order_diff,
        "missing": missing,
        "extra": extras,
        "summary": summary,
        "diff": diff,
        "row_count": None,
    }


def _row_to_payload(template: Template, headers: list[str], row: list[Any]) -> dict[str, Any]:
    idx = {str(h).strip(): i for i, h in enumerate(headers)}
    payload: dict[str, Any] = {}
    for col in template.columns:
        i = idx.get(col)
        if i is None:
            payload[col] = ""
        else:
            val = row[i] if i < len(row) else ""
            payload[col] = "" if val is None else val
    return payload


def _normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _required_columns(template: Template) -> list[str]:
    cols = list(template.columns)
    keys = list(template.unique_key or [])
    return list(dict.fromkeys([cols[0], *keys])) if cols else keys


def preview_rows(
    template: Template,
    headers: list[str],
    rows: list[list[Any]],
    existing_hashes: set[str],
) -> dict[str, Any]:
    cols = list(template.columns)
    req_cols = _required_columns(template)
    seen: set[str] = set()
    preview: list[dict[str, Any]] = []
    ok_count = dup_count = err_count = 0

    for row in rows:
        payload = _row_to_payload(template, headers, row)
        for col in cols:
            if isinstance(payload.get(col), str):
                payload[col] = payload[col].strip()

        status = "ok"
        msg = ""
        empty = [c for c in req_cols if _normalize_cell(payload.get(c)) == ""]
        if empty:
            status = "err"
            msg = f"{empty[0]}为空"
        elif "事业部" in cols:
            bu = _normalize_cell(payload.get("事业部"))
            if bu and bu not in BU_UNITS:
                status = "err"
                msg = "事业部非法值"

        if status == "ok":
            uk_hash = compute_uk_hash(template.unique_key, payload)
            if uk_hash in existing_hashes or uk_hash in seen:
                status = "dup"
            seen.add(uk_hash)

        if status == "ok":
            ok_count += 1
        elif status == "dup":
            dup_count += 1
        else:
            err_count += 1

        preview.append({"data": payload, "status": status, "msg": msg})

    return {
        "rows": preview,
        "ok_count": ok_count,
        "dup_count": dup_count,
        "err_count": err_count,
    }


async def load_existing_hashes(db: AsyncSession, l3_id: str) -> set[str]:
    result = await db.execute(select(DataRecord.uk_hash).where(DataRecord.l3_id == l3_id))
    return {row[0] for row in result.all()}


async def commit_rows(
    db: AsyncSession,
    l3_id: str,
    template: Template,
    headers: list[str],
    rows: list[list[Any]],
    dup_strategy: str,
) -> dict[str, Any]:
    if dup_strategy not in {"skip", "overwrite", "add"}:
        raise ValueError("invalid dup_strategy")

    existing_hashes = await load_existing_hashes(db, l3_id)
    preview = preview_rows(template, headers, rows, existing_hashes)

    inserted = 0
    updated = 0
    skipped = 0
    errors = preview["err_count"]

    hash_to_record: dict[str, DataRecord] = {}
    if dup_strategy == "overwrite":
        result = await db.execute(select(DataRecord).where(DataRecord.l3_id == l3_id))
        for record in result.scalars().all():
            hash_to_record[record.uk_hash] = record

    for row_index, item in enumerate(preview["rows"]):
        if item["status"] == "err":
            continue
        payload = item["data"]
        uk_hash = compute_uk_hash(template.unique_key, payload)

        if item["status"] == "dup":
            if dup_strategy == "skip":
                skipped += 1
                continue
            if dup_strategy == "overwrite":
                record = hash_to_record.get(uk_hash)
                if record:
                    record.payload = payload
                    updated += 1
                    continue
            # add: try insert; duplicate uk_hash in DB will be skipped below

        existing = hash_to_record.get(uk_hash) if dup_strategy == "overwrite" else None
        if existing:
            existing.payload = payload
            updated += 1
            continue

        if uk_hash in existing_hashes and dup_strategy == "add":
            skipped += 1
            continue

        db.add(
            DataRecord(
                l3_id=l3_id,
                payload=payload,
                uk_hash=uk_hash,
                source="import",
            )
        )
        inserted += 1
        existing_hashes.add(uk_hash)

    await db.commit()
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "committed": inserted + updated,
    }
