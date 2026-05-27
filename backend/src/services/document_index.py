from __future__ import annotations

import asyncio

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import DocChunk, Document
from src.services.document_parser import chunk_text, extract_text
from src.services.llm.dashscope import embed_document_texts
from src.services.rag_search import vector_literal


async def index_document(db: AsyncSession, document: Document, file_bytes: bytes) -> int:
    await db.execute(delete(DocChunk).where(DocChunk.document_id == document.id))

    try:
        raw = extract_text(document.file_name, file_bytes)
    except ValueError:
        document.index_status = "failed"
        await db.commit()
        return 0

    pieces = chunk_text(raw)
    if not pieces:
        document.index_status = "failed"
        await db.commit()
        return 0

    chunk_ids: list[int] = []
    for seq, piece in enumerate(pieces, start=1):
        chunk = DocChunk(
            document_id=document.id,
            seq=seq,
            title_path=document.file_name,
            text=piece,
        )
        db.add(chunk)
        await db.flush()
        chunk_ids.append(chunk.id)
        await db.execute(
            text("UPDATE doc_chunk SET tsv = to_tsvector('simple', :txt) WHERE id = :id"),
            {"txt": piece, "id": chunk.id},
        )

    embeddings = await asyncio.to_thread(embed_document_texts, pieces)
    for chunk_id, piece, emb in zip(chunk_ids, pieces, embeddings, strict=True):
        if not emb:
            continue
        await db.execute(
            text("UPDATE doc_chunk SET embedding = CAST(:vec AS vector) WHERE id = :id"),
            {"vec": vector_literal(emb), "id": chunk_id},
        )

    document.index_status = "indexed"
    await db.commit()
    return len(pieces)


def document_to_item(doc: Document) -> dict:
    return {
        "id": doc.id,
        "l3_id": doc.l3_id,
        "file_name": doc.file_name,
        "remark": doc.remark or "",
        "uploader": doc.uploader or "",
        "time": doc.created_at.strftime("%Y-%m-%d %H:%M") if doc.created_at else "",
        "meta": doc.meta,
        "version": doc.version,
        "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
        "is_current": doc.is_current,
        "index_status": doc.index_status,
    }
