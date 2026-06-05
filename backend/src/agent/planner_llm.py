"""Planner LLM — intent classification and plan generation (primary path)."""

from __future__ import annotations

import json
import re
from typing import Any

from src.agent.planner_rules import (
    CHITCHAT_GREETING_REPLY,
    INTENT_CONFIDENCE_THRESHOLD,
    INTENT_MODE,
    INTENT_UNMATCHED_MESSAGE,
    build_plan,
    classify_chitchat,
    classify_intent,
    is_followup_with_hint,
    is_org_metric_question,
    is_org_structured_question,
    is_policy_question,
)
from src.agent.catalog import catalog_prompt_block, is_document_l3, is_structured_l3, valid_l3_ids
from src.agent.prompts import PLANNER_FEW_SHOT, PLANNER_SYSTEM, with_global_preamble
from src.agent.router_loader import inject_router
from src.services.llm.dashscope import chat_completion

_VALID_INTENTS = frozenset({"chitchat", "policy", "lookup", "list", "aggregate", "trend", "forecast", "compare", "attribution"})
_VALID_SUBTASK_TYPES = frozenset({"resolve", "retrieve", "analyze", "critique", "compose"})
_TYPE_AGENT = {
    "resolve": "Resolver",
    "retrieve": "Retriever",
    "analyze": "Analyst",
    "critique": "Critic",
    "compose": "Composer",
}
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


_CATALOG_HEADER = """
## 可用数据分类目录

以下是全部可用数据分类目录。所有 retrieve 子任务的 target_l3 只能从本目录选取；
文档(RAG)类分类只能配 retrieve_mode="rag"，结构化分类只能配 "structured"。

"""


def _planner_system_prompt() -> str:
    catalog_block = _CATALOG_HEADER + catalog_prompt_block()
    agent = inject_router(f"{PLANNER_SYSTEM}\n\n{catalog_block}\n\n{PLANNER_FEW_SHOT}")
    return with_global_preamble(agent)


def _build_user_prompt(
    question: str,
    *,
    history: list[dict[str, Any]] | None = None,
    intent_hint: str | None = None,
    replan_gaps: list[str] | None = None,
) -> str:
    parts = [f"用户问题：{question.strip()}"]
    if intent_hint:
        parts.append(f"上一轮意图（仅供参考）：{intent_hint}")
    if replan_gaps:
        parts.append("上一轮质检缺口：" + "；".join(replan_gaps))
        parts.append("请在新计划中补足对应取证路（可换库或追加 retrieve 子任务）。")
    if history:
        recent = history[-2:]
        lines = [f"- Q: {h.get('question', '')} → intent={h.get('intent', '')}" for h in recent if h.get("question")]
        if lines:
            parts.append("最近对话：\n" + "\n".join(lines))
    parts.append("请输出 JSON：")
    return "\n\n".join(parts)


def _parse_json_response(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(stripped)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _normalize_plan_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    stype = item.get("type")
    if stype not in _VALID_SUBTASK_TYPES:
        return None
    out: dict[str, Any] = {
        "id": str(item.get("id") or "t1"),
        "type": stype,
        "goal": str(item.get("goal") or ""),
        "assigned_agent": _TYPE_AGENT[stype],
    }
    if stype == "retrieve":
        mode = item.get("retrieve_mode") or "structured"
        out["retrieve_mode"] = mode
        targets = item.get("target_l3") or []
        if isinstance(targets, list):
            out["target_l3"] = [str(x) for x in targets if x]
        else:
            out["target_l3"] = []
        group_by = item.get("group_by") or []
        if isinstance(group_by, list) and group_by:
            out["group_by"] = [str(x) for x in group_by if x]
        aggregations = item.get("aggregations") or []
        if isinstance(aggregations, list) and aggregations:
            out["aggregations"] = aggregations
    return out


def validate_plan_invariants(plan: list[dict[str, Any]]) -> bool:
    """Check plan DAG invariants (I1–I7). Intent-agnostic."""
    if not plan or len(plan) > 10:
        return False

    types = [p.get("type") for p in plan]
    if any(t not in _VALID_SUBTASK_TYPES for t in types):
        return False

    compose_idxs = [i for i, t in enumerate(types) if t == "compose"]
    if len(compose_idxs) != 1 or compose_idxs[0] != len(types) - 1:
        return False

    if "analyze" in types:
        analyze_idx = types.index("analyze")
        if "retrieve" not in types[:analyze_idx]:
            return False
        if "critique" not in types:
            return False
        critique_idx = types.index("critique")
        if not (analyze_idx < critique_idx < compose_idxs[0]):
            return False

    catalog_ids = valid_l3_ids()
    for item in plan:
        if item.get("type") != "retrieve":
            continue
        targets = item.get("target_l3") or []
        if not targets or any(tid not in catalog_ids for tid in targets):
            return False
        mode = item.get("retrieve_mode") or "structured"
        if mode == "rag":
            if not all(is_document_l3(tid) for tid in targets):
                return False
        elif mode == "structured":
            if not all(is_structured_l3(tid) for tid in targets):
                return False
        else:
            return False

    return True


def _validate_plan(intent: str, plan: list[dict[str, Any]], question: str) -> bool:
    if intent not in _VALID_INTENTS:
        return False
    return validate_plan_invariants(plan)


def _chitchat_result(*, reply: str, source: str, reasoning: str = "寒暄/自我介绍，短路回复") -> dict[str, Any]:
    return {
        "intent": "chitchat",
        "reply": reply,
        "chitchat": True,
        "reasoning": reasoning,
        "plan": [],
        "source": source,
    }


def _unmatched_result(*, reasoning: str, source: str) -> dict[str, Any]:
    return {
        "intent": None,
        "unmatched": True,
        "reasoning": reasoning,
        "plan": [],
        "source": source,
    }


def _parse_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def plan_with_llm(
    question: str,
    *,
    history: list[dict[str, Any]] | None = None,
    intent_hint: str | None = None,
    replan_gaps: list[str] | None = None,
) -> dict[str, Any] | None:
    """Return plan dict, unmatched dict, or None when LLM unavailable/invalid."""
    raw = chat_completion(
        messages=[
            {"role": "system", "content": _planner_system_prompt()},
            {
                "role": "user",
                "content": _build_user_prompt(
                    question,
                    history=history,
                    intent_hint=intent_hint,
                    replan_gaps=replan_gaps,
                ),
            },
        ],
        temperature=0.1,
        max_tokens=1200,
    )
    payload = _parse_json_response(raw or "")
    if not payload:
        return None

    if payload.get("reject"):
        return None

    intent = str(payload.get("intent") or "").strip()
    if intent == "chitchat":
        reply = str(payload.get("reply") or "").strip()
        if not reply:
            ruled = classify_chitchat(question)
            reply = (ruled or {}).get("reply") or CHITCHAT_GREETING_REPLY
        reasoning = str(payload.get("reasoning") or "").strip()
        return _chitchat_result(reply=reply, source="llm", reasoning=reasoning or "LLM 判定闲聊短路")

    confidence = _parse_confidence(payload.get("confidence"))
    if confidence is not None and confidence < INTENT_CONFIDENCE_THRESHOLD:
        return _unmatched_result(reasoning=f"置信度过低({confidence})", source="llm")

    intent = str(payload.get("intent") or "").strip()

    # 透传 LLM 的薪资语义判定字段（ROUTER §4 出口2）
    payroll_sensitive = bool(payload.get("payroll_sensitive"))
    payroll_scope_raw = payload.get("payroll_scope")
    payroll_scope = (
        str(payroll_scope_raw).strip()
        if payroll_scope_raw and str(payroll_scope_raw).strip() in {"individual", "bu", "company"}
        else None
    )

    # intent=clarify：薪资明细范围过大需澄清，由 Planner 直接出 clarify 出口（无 plan）
    if intent == "clarify":
        clarify_raw = payload.get("clarify") or {}
        if not isinstance(clarify_raw, dict):
            return None
        return {
            "intent": "clarify",
            "reasoning": str(payload.get("reasoning") or "").strip() or "需要补充信息",
            "plan": [],
            "clarify": clarify_raw,
            "payroll_sensitive": payroll_sensitive,
            "payroll_scope": payroll_scope or "company",
        }

    plan_raw = payload.get("plan") or payload.get("subtasks") or []
    if not isinstance(plan_raw, list):
        return None

    if not intent or not plan_raw:
        return _unmatched_result(reasoning="LLM 未识别有效 intent", source="llm")

    if intent == "policy" and not is_policy_question(question):
        return _unmatched_result(reasoning="不满足 policy 白名单", source="llm")

    plan: list[dict[str, Any]] = []
    for item in plan_raw:
        normalized = _normalize_plan_item(item)
        if normalized:
            plan.append(normalized)
    if not _validate_plan(intent, plan, question):
        return None

    reasoning = str(payload.get("reasoning") or "").strip()
    out: dict[str, Any] = {
        "intent": intent,
        "reasoning": reasoning,
        "plan": plan,
        "payroll_sensitive": payroll_sensitive,
        "payroll_scope": payroll_scope,
    }
    if confidence is not None:
        out["confidence"] = confidence
    return out


def plan_with_rules(
    question: str,
    *,
    intent_hint: str | None = None,
    entities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rule-based fallback when LLM planning is unavailable."""
    intent = classify_intent(question, hint=intent_hint)
    if intent is None:
        return _unmatched_result(reasoning="规则引擎未匹配任何意图", source="rules")
    return {
        "intent": intent,
        "reasoning": "规则引擎匹配",
        "plan": build_plan(intent, question, entities=entities or {}),
        "source": "rules",
    }


def resolve_plan(
    question: str,
    *,
    history: list[dict[str, Any]] | None = None,
    intent_hint: str | None = None,
    entities: dict[str, Any] | None = None,
    replan_gaps: list[str] | None = None,
) -> dict[str, Any]:
    """Primary: chitchat → LLM → rules; unmatched when no business intent applies."""
    if not is_followup_with_hint(question, intent_hint):
        chitchat = classify_chitchat(question)
        if chitchat:
            return _chitchat_result(reply=chitchat["reply"], source="rules", reasoning="规则判定闲聊短路")

    if is_org_structured_question(question):
        rules = plan_with_rules(question, intent_hint=intent_hint, entities=entities)
        if rules.get("unmatched"):
            return rules
        rules["source"] = "rules"
        rules["reasoning"] = "组织指标问法，使用结构化聚合/趋势路径（非个人 lookup）"
        return rules

    llm = plan_with_llm(
        question,
        history=history,
        intent_hint=intent_hint,
        replan_gaps=replan_gaps,
    )
    if llm:
        if llm.get("chitchat") or llm.get("unmatched"):
            return llm
        if llm.get("intent") == "lookup" and is_org_structured_question(question):
            corrected = plan_with_rules(question, intent_hint=intent_hint, entities=entities)
            corrected["source"] = "rules"
            corrected["reasoning"] = "组织指标问法，纠正为结构化聚合/趋势（非个人 lookup）"
            return corrected
        llm["source"] = "llm"
        return llm

    rules = plan_with_rules(question, intent_hint=intent_hint, entities=entities)
    return rules


def planner_trace_summary(intent: str, question: str, *, reasoning: str, source: str) -> str:
    q_preview = question.strip()
    if len(q_preview) > 32:
        q_preview = q_preview[:32] + "…"
    mode = INTENT_MODE.get(str(intent), str(intent))
    src = "LLM" if source == "llm" else "规则"
    reason = reasoning[:48] + ("…" if len(reasoning) > 48 else "")
    return f"识别意图：{intent}（{mode}）· {reason} · [{src}] · 「{q_preview}」"
