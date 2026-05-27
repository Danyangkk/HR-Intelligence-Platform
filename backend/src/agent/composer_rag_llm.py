"""Composer RAG answer draft — policy intent only."""

from __future__ import annotations

import asyncio
from typing import Any

from src.agent.prompts import RAG_ANSWER_SYSTEM, with_global_preamble
from src.services.llm.dashscope import chat_completion


def _format_hits(hits: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for idx, hit in enumerate(hits[:5], start=1):
        title = hit.get("title_path")
        if isinstance(title, list):
            title = " / ".join(str(x) for x in title)
        parts.append(
            f"[{idx}] 文档片段\n"
            f"  文档/章节: {title or hit.get('doc_id')}\n"
            f"  seq: {hit.get('seq')}\n"
            f"  正文: {str(hit.get('text') or '')[:800]}\n"
            f"  score: {hit.get('score')}"
        )
    return "\n\n".join(parts)


def _build_user_prompt(question: str, hits: list[dict[str, Any]]) -> str:
    return (
        f"问题：{question.strip()}\n\n"
        f"检索片段(含 文档名/章节/正文/匹配度)：\n{_format_hits(hits)}\n\n"
        "请输出答案正文 + 末尾「出处：」列表。"
    )


async def rag_answer_draft(question: str, hits: list[dict[str, Any]]) -> str | None:
    if not hits:
        return None
    system = with_global_preamble(RAG_ANSWER_SYSTEM)
    user = _build_user_prompt(question, hits)
    draft = await asyncio.to_thread(
        chat_completion,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=1200,
    )
    text = (draft or "").strip()
    return text if len(text) >= 8 else None
