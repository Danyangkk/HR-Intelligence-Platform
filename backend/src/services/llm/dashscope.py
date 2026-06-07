from __future__ import annotations

from typing import Any

import httpx

from pycore.core.logger import get_logger
from src.core.config import get_settings

logger = get_logger()

EMBED_URL = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
EMBED_MODEL = "text-embedding-v3"
RERANK_MODEL = "gte-rerank-v2"
EMBED_DIM = 1024
EMBED_BATCH = 10

MISSING_DASHSCOPE_KEY_MESSAGE = "未配置模型 Key，请在 .env 填入 DASHSCOPE_API_KEY"


def is_dashscope_configured() -> bool:
    return bool(_api_key())


def _api_key() -> str:
    return (get_settings().dashscope_api_key or "").strip()


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _embed_batch(texts: list[str], *, text_type: str) -> list[list[float] | None]:
    api_key = _api_key()
    if not api_key or not texts:
        return [None] * len(texts)

    payload = {
        "model": EMBED_MODEL,
        "input": {"texts": texts},
        "parameters": {"text_type": text_type, "dimension": EMBED_DIM},
    }
    try:
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            resp = client.post(EMBED_URL, headers=_headers(api_key), json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("DashScope embedding request failed", error_msg=str(exc))
        return [None] * len(texts)

    if data.get("code"):
        logger.warning("DashScope embedding error", api_code=data.get("code"), detail=data.get("message"))
        return [None] * len(texts)

    by_index: dict[int, list[float]] = {}
    for item in (data.get("output") or {}).get("embeddings") or []:
        idx = item.get("text_index", 0)
        vec = item.get("embedding")
        if isinstance(vec, list) and vec:
            by_index[int(idx)] = [float(v) for v in vec]

    return [by_index.get(i) for i in range(len(texts))]


def embed_document_texts(texts: list[str]) -> list[list[float] | None]:
    if not texts:
        return []
    results: list[list[float] | None] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        results.extend(_embed_batch(batch, text_type="document"))
    return results


def embed_query(text: str) -> list[float] | None:
    if not text.strip():
        return None
    vecs = _embed_batch([text], text_type="query")
    return vecs[0] if vecs else None


def rerank_documents(query: str, documents: list[str], top_n: int) -> list[dict[str, Any]]:
    api_key = _api_key()
    if not api_key or not documents or not query.strip():
        return []

    payload = {
        "model": RERANK_MODEL,
        "input": {"query": query, "documents": documents},
        "parameters": {"top_n": min(top_n, len(documents)), "return_documents": False},
    }
    try:
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            resp = client.post(RERANK_URL, headers=_headers(api_key), json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("DashScope rerank request failed", error_msg=str(exc))
        return []

    if data.get("code"):
        logger.warning("DashScope rerank error", api_code=data.get("code"), detail=data.get("message"))
        return []

    return list((data.get("output") or {}).get("results") or [])


CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


def _chat_model(model: str | None = None) -> str:
    if model:
        return model
    return (get_settings().dashscope_chat_model or "qwen-long").strip() or "qwen-long"


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1200,
) -> str | None:
    """Sync chat completion via DashScope OpenAI-compatible API. Returns None on failure."""
    api_key = _api_key()
    if not api_key:
        return None
    model_name = _chat_model(model)
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            resp = client.post(CHAT_URL, headers=_headers(api_key), json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("DashScope chat request failed", error_msg=str(exc))
        return None

    if data.get("code"):
        logger.warning("DashScope chat error", api_code=data.get("code"), detail=data.get("message"))
        return None

    choices = data.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    return str(content).strip() if content else None
