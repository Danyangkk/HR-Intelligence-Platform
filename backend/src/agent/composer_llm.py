"""Composer LLM polish — rewrite draft answers into user-friendly HR language."""

from __future__ import annotations

import asyncio
from typing import Any

from src.agent.prompts import COMPOSER_POLISH_SYSTEM, with_global_preamble
from src.agent.state import AgentState
from src.services.llm.dashscope import chat_completion

_SYSTEM_PROMPT = with_global_preamble(COMPOSER_POLISH_SYSTEM)


def _build_user_prompt(state: AgentState, draft: str) -> str:
    question = (state.get("question") or "").strip()
    intent = state.get("intent") or "unknown"
    limitation = (state.get("limitation") or "").strip()
    parts = [
        f"用户问题：{question}",
        f"意图类型：{intent}",
        f"草稿答案：\n{draft.strip()}",
    ]
    if limitation:
        parts.append(f"补充说明（需保留）：{limitation}")
    parts.append("请输出用户友好的最终回复：")
    return "\n\n".join(parts)


async def polish_answer(draft: str, state: AgentState) -> str:
    """Return LLM-polished text, or the original draft when LLM is unavailable."""
    text = (draft or "").strip()
    if not text:
        return draft
    if state.get("rejected") or state.get("clarify"):
        return draft

    prompt = _build_user_prompt(state, text)
    polished = await asyncio.to_thread(
        chat_completion,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1200,
    )
    if polished and len(polished.strip()) >= max(8, len(text) // 4):
        return polished.strip()
    return draft
