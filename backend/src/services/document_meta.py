"""LLM metadata extraction for report documents."""

from __future__ import annotations

import re
from typing import Any

from src.agent.llm_runner import parse_json_response
from src.agent.prompts import METADATA_EXTRACTOR_SYSTEM, with_global_preamble
from src.core.constants import BU_UNITS
from src.services.llm.dashscope import chat_completion

_JSON_FIELDS = ("业务域", "周期", "事业部", "类型", "摘要")


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


def extract_report_meta(document_text: str, *, filename: str = "") -> dict[str, str]:
    llm_meta = extract_report_meta_llm(document_text, filename=filename)
    if llm_meta:
        return llm_meta
    return _guess_report_meta(filename)


def extract_report_meta_llm(document_text: str, *, filename: str = "") -> dict[str, str] | None:
    text = (document_text or "").strip()
    if not text:
        return None
    excerpt = text[:6000]
    user = f"文件名：{filename}\n\n文档全文：\n{excerpt}\n\n只输出 JSON。"
    raw = chat_completion(
        messages=[
            {"role": "system", "content": with_global_preamble(METADATA_EXTRACTOR_SYSTEM)},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=400,
    )
    payload = parse_json_response(raw or "")
    if not payload:
        return None
    meta: dict[str, str] = {}
    for key in _JSON_FIELDS:
        val = str(payload.get(key) or "").strip()
        if key == "事业部" and val and val not in BU_UNITS:
            val = ""
        meta[key] = val
    return meta
