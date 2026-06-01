"""Layer 2: 检索质量 — 集合比对 expected_modules / expected_doc_chunks。

跑全流程（run_agent），从 final_state 抽出实际命中模块/文档片段：
  - 结构化模块：evidence 里 kind=structured 的 l3_id → 通过 category 表名映射回中文模块名
  - 文档片段：evidence 里 kind=documents 的 hits[*].title_path
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Category


async def collect_actual_retrieval(
    db: AsyncSession, final_state: dict[str, Any]
) -> dict[str, list[str]]:
    """从 agent run 结果里抽出命中的模块名 + 文档段落标识。"""
    evidence = final_state.get("evidence") or []
    structured_l3s = {b.get("l3_id") for b in evidence if b.get("kind") == "structured" and b.get("l3_id")}
    structured_l3s.discard(None)
    modules: list[str] = []
    if structured_l3s:
        rows = (
            await db.execute(select(Category.id, Category.name).where(Category.id.in_(structured_l3s)))
        ).all()
        id_to_name = {rid: name for rid, name in rows}
        for l3 in structured_l3s:
            modules.append(id_to_name.get(l3, l3))

    doc_chunks: list[str] = []
    for b in evidence:
        if b.get("kind") != "documents":
            continue
        for h in b.get("hits") or []:
            tp = h.get("title_path") or h.get("section") or ""
            if tp:
                doc_chunks.append(tp)

    return {"modules": modules, "doc_chunks": doc_chunks}


def judge_layer2(
    case: dict[str, Any], actual_retrieval: dict[str, list[str]]
) -> dict[str, Any]:
    """集合比对：期望模块/文档段是否全部出现在 actual 里（子集即 pass，多了不扣）。"""
    expected = case.get("expected") or {}
    exp_modules = expected.get("expected_modules") or []
    exp_doc_chunks = expected.get("expected_doc_chunks") or []

    actual_modules = actual_retrieval.get("modules") or []
    actual_doc_chunks = actual_retrieval.get("doc_chunks") or []

    missing_modules = [m for m in exp_modules if not any(m in am for am in actual_modules)]
    missing_doc_chunks = [d for d in exp_doc_chunks if not any(_loose_match(d, ad) for ad in actual_doc_chunks)]

    passed = not missing_modules and not missing_doc_chunks
    return {
        "passed": passed,
        "actual": {"modules": actual_modules, "doc_chunks": actual_doc_chunks},
        "missing_modules": missing_modules,
        "missing_doc_chunks": missing_doc_chunks,
    }


def _loose_match(expected: str, actual: str) -> bool:
    """文档片段宽松匹配：标题或编号子串相互包含都算命中。"""
    if not expected or not actual:
        return False
    return expected in actual or actual in expected
