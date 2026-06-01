"""Layer 3: 答案质量 — LLM-as-judge 按 rubric 打分。

每条 case 调一次 LLM。单条失败 try/except 兜底（不影响整批）。
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.eval.prompts import JUDGE_SYSTEM, build_judge_user_prompt
from src.services.llm.dashscope import chat_completion


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def judge_layer3(case: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """跑一次 LLM-as-judge。返回 {scored, score_detail, error}。

    错误处理（规格 §错误处理）：LLM 失败 / 解析失败 → scored=False，记 error；整批继续。
    """
    try:
        user_msg = build_judge_user_prompt(case, actual)
        text = chat_completion(
            [
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=600,
        )
    except Exception as exc:  # noqa: BLE001
        return {"scored": False, "error": f"llm_call_failed: {exc}"}

    if not text:
        return {"scored": False, "error": "llm_no_response"}

    parsed = _parse_judge_json(text)
    if not parsed:
        return {"scored": False, "error": f"judge_parse_failed: {text[:200]}", "raw": text[:500]}

    score_detail = _normalize_rubric(parsed)
    return {
        "scored": True,
        "score_detail": score_detail,
        "judge_reasoning": score_detail.get("reasoning") or "",
        "violations": score_detail.get("violations") or [],
        "overall": score_detail.get("overall"),
    }


def _parse_judge_json(text: str) -> dict[str, Any] | None:
    """从 LLM 输出里抽 JSON。优先整体 parse；不行就用第一个 `{...}` 块。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        # 处理 ```json ... ``` 包裹
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None
    return None


def _normalize_rubric(parsed: dict[str, Any]) -> dict[str, Any]:
    """把 rubric 4 维 clamp 到 1-5 整数；overall 缺省时取 4 维均值。"""
    def _clamp(v: Any) -> float:
        try:
            n = float(v)
        except (TypeError, ValueError):
            return 0.0
        return max(1.0, min(5.0, n))

    correctness = _clamp(parsed.get("correctness"))
    completeness = _clamp(parsed.get("completeness"))
    citation = _clamp(parsed.get("citation"))
    compliance = _clamp(parsed.get("compliance"))
    overall_raw = parsed.get("overall")
    if overall_raw is None:
        overall = round((correctness + completeness + citation + compliance) / 4.0, 2)
    else:
        overall = _clamp(overall_raw)
    return {
        "correctness": correctness,
        "completeness": completeness,
        "citation": citation,
        "compliance": compliance,
        "overall": overall,
        "reasoning": str(parsed.get("reasoning") or "")[:1000],
        "violations": parsed.get("violations") or [],
    }
