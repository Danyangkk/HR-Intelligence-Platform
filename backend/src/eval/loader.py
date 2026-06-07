"""加载 eval_set.yaml 并规范化字段。

eval_set.yaml 只读：系统代码不得写入该文件；入集唯一通道是人工编辑 YAML 后走 Git。

case schema:
    id: str
    query: str
    role: str (default biz_super_admin)
    layer: list[int]  # 哪些层参与评测
    history: list[dict] (default [])
    expected:
      intent: str
      reject: bool
      chitchat: bool
      reply_contains: list[str]
      expected_modules: list[str]
      expected_doc_chunks: list[str]
      answer_points: list[str]
      expected_citations: list[dict]
      forbid: list[str]
      forbid_path: list[str]
      metric_callouts: list[str]
      must_load_skills: list[str]
      clarify_or_inherit: bool
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

EVAL_SET_PATH = Path(__file__).resolve().parents[2] / "eval" / "eval_set.yaml"

DEFAULT_ROLE = "biz_super_admin"  # 默认业务超管，已自带薪资权（layer3 个人薪资类 case 才能跑全流程）


def load_eval_set(path: Path | None = None) -> list[dict[str, Any]]:
    """加载 eval_set.yaml。"""
    p = path or EVAL_SET_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{p} must be a list")
    cases: list[dict[str, Any]] = []
    for raw_case in raw:
        if not isinstance(raw_case, dict):
            continue
        case = _normalize(raw_case)
        cases.append(case)
    return cases


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    layer = raw.get("layer") or [1]
    if isinstance(layer, int):
        layer = [layer]
    return {
        "id": str(raw["id"]),
        "query": str(raw.get("query") or ""),
        "role": str(raw.get("role") or DEFAULT_ROLE),
        "layer": [int(x) for x in layer],
        "history": list(raw.get("history") or []),
        "expected": dict(raw.get("expected") or {}),
    }


def get_case_intent(case: dict[str, Any]) -> str | None:
    return case.get("expected", {}).get("intent")


def filter_layer(cases: list[dict[str, Any]], layer: int) -> list[dict[str, Any]]:
    return [c for c in cases if layer in c.get("layer", [])]
