from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.llm.dashscope import embed_query, rerank_documents

RRF_K = 60
RECALL_K = 20
RERANK_MIN_SCORE = 0.15
ALLOWED_META_KEYS = frozenset({"业务域", "周期", "事业部", "类型", "摘要"})


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(v) for v in values) + "]"


def _meta_filter_sql(meta_filters: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    if not meta_filters:
        return "", {}
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for idx, (key, value) in enumerate(meta_filters.items()):
        if value is None or value == "" or key not in ALLOWED_META_KEYS:
            continue
        pname = f"mf_{idx}"
        clauses.append(f"d.meta->>'{key}' = :{pname}")
        params[pname] = str(value)
    if not clauses:
        return "", {}
    return " AND " + " AND ".join(clauses), params


def _rrf_fuse(vector_rows: list, bm25_rows: list) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for rank, row in enumerate(vector_rows, start=1):
        cid = int(row.id)
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    for rank, row in enumerate(bm25_rows, start=1):
        cid = int(row.id)
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def _row_map(rows: list) -> dict[int, Any]:
    return {int(row.id): row for row in rows}


async def search_documents(
    db: AsyncSession,
    *,
    l3_id: str,
    query: str,
    top_k: int = 5,
    meta_filters: dict[str, Any] | None = None,
    only_current: bool = True,
) -> dict[str, Any]:
    q = query.strip()
    if not q:
        return {"hits": [], "mode": "empty", "found": False}

    meta_sql, meta_params = _meta_filter_sql(meta_filters)
    current_sql = (
        " AND (d.doc_kind = 'report' OR d.is_current IS DISTINCT FROM false)"
        if only_current
        else ""
    )
    base_where = f"d.l3_id = :l3_id{current_sql}{meta_sql}"
    params: dict[str, Any] = {"l3_id": l3_id, **meta_params}

    query_vec = await asyncio.to_thread(embed_query, q)
    vector_rows: list = []
    if query_vec:
        vec_params = {**params, "query_vec": vector_literal(query_vec), "limit": RECALL_K}
        vec_result = await db.execute(
            text(
                f"""
                SELECT c.id, c.document_id, c.seq, c.title_path, c.text,
                       1 - (c.embedding <=> CAST(:query_vec AS vector)) AS score
                FROM doc_chunk c
                JOIN document d ON d.id = c.document_id
                WHERE {base_where}
                  AND c.embedding IS NOT NULL
                ORDER BY c.embedding <=> CAST(:query_vec AS vector)
                LIMIT :limit
                """
            ),
            vec_params,
        )
        vector_rows = list(vec_result.mappings().all())

    bm25_result = await db.execute(
        text(
            f"""
            SELECT c.id, c.document_id, c.seq, c.title_path, c.text,
                   ts_rank_cd(c.tsv, plainto_tsquery('simple', :q)) AS score
            FROM doc_chunk c
            JOIN document d ON d.id = c.document_id
            WHERE {base_where}
              AND c.tsv IS NOT NULL
              AND plainto_tsquery('simple', :q) @@ c.tsv
            ORDER BY score DESC
            LIMIT :limit
            """
        ),
        {**params, "q": q, "limit": RECALL_K},
    )
    bm25_rows = list(bm25_result.mappings().all())

    if not vector_rows and not bm25_rows:
        return {"hits": [], "mode": "none", "found": False}

    if vector_rows and bm25_rows:
        fused = _rrf_fuse(vector_rows, bm25_rows)
        mode = "hybrid"
    elif vector_rows:
        fused = [(int(r.id), float(r.score or 0)) for r in vector_rows]
        mode = "vector"
    else:
        fused = [(int(r.id), float(r.score or 0)) for r in bm25_rows]
        mode = "bm25"

    row_lookup = _row_map(vector_rows + bm25_rows)
    candidates: list[tuple[int, float, Any]] = []
    seen: set[int] = set()
    for chunk_id, score in fused:
        if chunk_id in seen:
            continue
        row = row_lookup.get(chunk_id)
        if row is None:
            continue
        seen.add(chunk_id)
        candidates.append((chunk_id, score, row))
        if len(candidates) >= RECALL_K:
            break

    rerank_results = await asyncio.to_thread(
        rerank_documents,
        q,
        [str(c[2].text) for c in candidates],
        top_k,
    )
    if rerank_results:
        hits = []
        for item in rerank_results:
            idx = int(item.get("index", -1))
            score = float(item.get("relevance_score") or 0)
            if score < RERANK_MIN_SCORE:
                continue
            if idx < 0 or idx >= len(candidates):
                continue
            _, _, row = candidates[idx]
            hits.append(
                {
                    "chunk_id": row.id,
                    "doc_id": row.document_id,
                    "seq": row.seq,
                    "title_path": row.title_path,
                    "text": row.text,
                    "score": score,
                }
            )
        mode = f"{mode}+rerank"

    else:
        hits = [
            {
                "chunk_id": row.id,
                "doc_id": row.document_id,
                "seq": row.seq,
                "title_path": row.title_path,
                "text": row.text,
                "score": float(score),
            }
            for _, score, row in candidates[:top_k]
        ]

    return {"hits": hits, "mode": mode, "found": len(hits) > 0}
