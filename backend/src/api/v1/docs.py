from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import BU_UNITS
from src.core.response import ok
from src.db.session import get_db
from src.models import DocChunk, Document
from src.services.document_index import document_to_item, index_document
from src.services.document_meta import extract_report_meta
from src.services.document_parser import extract_text
from src.services.rag_search import search_documents
from src.services.source import source_of
from src.services.storage import delete_object, new_object_key, presigned_get_url, upload_bytes

router = APIRouter(prefix="/docs", tags=["docs"])

REPORT_META_FIELDS = ("业务域", "周期", "事业部", "类型", "摘要")


async def _load_doc_l3(db: AsyncSession, l3_id: str, expected: str | set[str]) -> str:
    from src.models import Category

    cat = await db.get(Category, l3_id)
    if not cat or cat.level != 3:
        raise HTTPException(status_code=404, detail="category not found")
    src = cat.source or source_of(l3_id)
    allowed = {expected} if isinstance(expected, str) else expected
    if src not in allowed:
        raise HTTPException(status_code=400, detail=f"not a {expected} document category")
    return src


def _guess_report_meta(filename: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    name = filename
    if re.search(r"复盘|归因", name):
        meta["业务域"] = "离职归因"
        meta["类型"] = "复盘报告"
    elif re.search(r"支出|成本", name):
        meta["业务域"] = "成本"
        meta["类型"] = "复盘报告"
    elif re.search(r"调研", name):
        meta["业务域"] = "调研"
        meta["类型"] = "调研报告"
    q = re.search(r"20\d{2}\s*[Qq][1-4]|20\d{2}[-.]\d{1,2}|[Qq][1-4]", name)
    if q:
        meta["周期"] = q.group(0).replace(" ", "").replace(".", "-").upper()
    for bu in BU_UNITS:
        if bu.replace("部门", "") in name:
            meta["事业部"] = bu
    meta["摘要"] = "（自动提取的摘要占位，请根据原文校对）"
    return meta


@router.get("/{l3_id}")
async def list_docs(
    l3_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    src = await _load_doc_l3(db, l3_id, {"rule", "report"})
    query = select(Document).where(Document.l3_id == l3_id)
    if src == "rule":
        query = query.order_by(Document.is_current.desc(), Document.created_at.desc())
    else:
        query = query.order_by(Document.created_at.desc())

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    items = [document_to_item(doc) for doc in result.scalars().all()]
    return ok({"l3_id": l3_id, "items": items, "pagination": {"page": page, "page_size": page_size, "total": total}})


@router.get("/{l3_id}/{doc_id}")
async def get_doc(l3_id: str, doc_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await _load_doc_l3(db, l3_id, {"rule", "report"})
    doc = await db.get(Document, doc_id)
    if not doc or doc.l3_id != l3_id:
        raise HTTPException(status_code=404, detail="document not found")
    item = document_to_item(doc)
    if doc.file_key:
        item["file_url"] = presigned_get_url(doc.file_key)
    return ok(item)


@router.get("/{l3_id}/{doc_id}/chunks")
async def list_chunks(l3_id: str, doc_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await _load_doc_l3(db, l3_id, {"rule", "report"})
    doc = await db.get(Document, doc_id)
    if not doc or doc.l3_id != l3_id:
        raise HTTPException(status_code=404, detail="document not found")
    result = await db.execute(
        select(DocChunk).where(DocChunk.document_id == doc_id).order_by(DocChunk.seq)
    )
    chunks = [
        {"id": c.id, "seq": c.seq, "title_path": c.title_path, "text": c.text}
        for c in result.scalars().all()
    ]
    return ok({"l3_id": l3_id, "doc_id": doc_id, "chunks": chunks})


@router.post("/{l3_id}/upload")
async def upload_rule_doc(
    l3_id: str,
    file: UploadFile = File(...),
    remark: str = Form(""),
    version: str = Form(""),
    effective_date: str = Form(""),
    uploader: str = Form("HR 用户"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _load_doc_l3(db, l3_id, "rule")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    if version.strip():
        await db.execute(
            text("UPDATE document SET is_current = false WHERE l3_id = :l3_id AND is_current = true"),
            {"l3_id": l3_id},
        )

    eff: date | None = None
    if effective_date.strip():
        eff = date.fromisoformat(effective_date.strip())

    key = new_object_key(l3_id, file.filename or "upload.docx")
    upload_bytes(key, data, file.content_type or "application/octet-stream")

    doc = Document(
        l3_id=l3_id,
        file_name=file.filename or "upload.docx",
        file_key=key,
        remark=remark.strip() or None,
        doc_kind="rule",
        version=version.strip() or None,
        effective_date=eff,
        is_current=True,
        index_status="pending",
        uploader=uploader.strip() or None,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    chunk_count = await index_document(db, doc, data)
    return ok({**document_to_item(doc), "chunk_count": chunk_count})


@router.post("/{l3_id}/extract")
async def extract_report_meta(
    l3_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _load_doc_l3(db, l3_id, "report")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        text = extract_text(file.filename or "report.docx", data)
    except ValueError:
        text = ""
    meta = extract_report_meta(text, filename=file.filename or "")
    key = new_object_key(l3_id, file.filename or "report.docx")
    upload_bytes(key, data, file.content_type or "application/octet-stream")
    return ok(
        {
            "l3_id": l3_id,
            "file_name": file.filename,
            "file_key": key,
            "meta": meta,
            "pending": True,
        }
    )


@router.post("/{l3_id}/confirm")
async def confirm_report_doc(
    l3_id: str,
    file_name: str = Form(...),
    file_key: str = Form(...),
    domain: str = Form(""),
    period: str = Form(""),
    bu: str = Form(""),
    doc_type: str = Form(""),
    summary: str = Form(""),
    uploader: str = Form("HR 用户"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _load_doc_l3(db, l3_id, "report")
    meta = {
        "业务域": domain.strip(),
        "周期": period.strip(),
        "事业部": bu.strip(),
        "类型": doc_type.strip(),
        "摘要": summary.strip(),
    }
    doc = Document(
        l3_id=l3_id,
        file_name=file_name,
        file_key=file_key,
        meta=meta,
        doc_kind="report",
        is_current=True,
        index_status="pending",
        uploader=uploader.strip() or None,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    from src.services.storage import get_minio_client
    from src.core.config import get_settings

    settings = get_settings()
    client = get_minio_client()
    obj = client.get_object(settings.minio_bucket, file_key)
    data = obj.read()
    obj.close()
    chunk_count = await index_document(db, doc, data)
    return ok({**document_to_item(doc), "chunk_count": chunk_count})


@router.post("/{l3_id}/search")
async def search_docs(
    l3_id: str,
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _load_doc_l3(db, l3_id, {"rule", "report"})
    result = await search_documents(db, l3_id=l3_id, query=q, top_k=top_k, only_current=True)
    return ok(
        {
            "l3_id": l3_id,
            "query": q,
            "hits": result["hits"],
            "found": result["found"],
            "mode": result["mode"],
        }
    )


@router.delete("/{l3_id}")
async def delete_docs(
    l3_id: str,
    body: dict[str, list[int]],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _load_doc_l3(db, l3_id, {"rule", "report"})
    ids = body.get("ids") or []
    if not ids:
        return ok({"deleted": 0})

    result = await db.execute(select(Document).where(Document.l3_id == l3_id, Document.id.in_(ids)))
    docs = list(result.scalars().all())
    for doc in docs:
        if doc.file_key:
            try:
                delete_object(doc.file_key)
            except Exception:
                pass
        await db.delete(doc)
    await db.commit()
    return ok({"deleted": len(docs), "ids": [d.id for d in docs]})
