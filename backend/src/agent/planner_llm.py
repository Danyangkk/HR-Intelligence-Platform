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
    NAME_RE,
    build_plan,
    classify_chitchat,
    classify_intent,
    is_followup_with_hint,
    is_org_metric_question,
    is_org_structured_question,
    is_personal_lookup_question,
    is_policy_question,
    is_procedure_question,
)
from src.agent.prompts import PLANNER_FEW_SHOT, PLANNER_SYSTEM, with_global_preamble
from src.agent.router_loader import inject_router
from src.services.llm.dashscope import chat_completion

_VALID_INTENTS = frozenset({"chitchat", "policy", "lookup", "list", "aggregate", "trend", "forecast", "compare", "attribution"})
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _planner_system_prompt() -> str:
    agent = inject_router(f"{PLANNER_SYSTEM}\n\n{PLANNER_FEW_SHOT}")
    return with_global_preamble(agent)


def _build_user_prompt(
    question: str,
    *,
    history: list[dict[str, Any]] | None = None,
    intent_hint: str | None = None,
) -> str:
    parts = [f"用户问题：{question.strip()}"]
    if intent_hint:
        parts.append(f"上一轮意图（仅供参考）：{intent_hint}")
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
    agent = item.get("assigned_agent")
    if not stype or not agent:
        return None
    out: dict[str, Any] = {
        "id": str(item.get("id") or "t1"),
        "type": stype,
        "goal": str(item.get("goal") or ""),
        "assigned_agent": agent,
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


def _validate_plan(intent: str, plan: list[dict[str, Any]], question: str) -> bool:
    if intent not in _VALID_INTENTS or not plan:
        return False
    types = [p.get("type") for p in plan]
    if intent == "policy":
        if types != ["retrieve", "compose"]:
            return False
        retrieve = plan[0]
        if retrieve.get("retrieve_mode") != "rag":
            return False
        if "l3-1-1-1" not in (retrieve.get("target_l3") or []):
            return False
    if intent == "lookup":
        if not is_personal_lookup_question(question):
            return False
        if types[:2] != ["resolve", "retrieve"] or "compose" not in types:
            return False
        if plan[1].get("retrieve_mode") != "structured":
            return False
    if intent == "list":
        if types[:2] != ["resolve", "retrieve"] or types[-1] != "compose":
            return False
    if intent == "aggregate":
        if types[:2] != ["resolve", "retrieve"] or types[-1] != "compose":
            return False
    if intent == "trend":
        required = {"resolve", "retrieve", "analyze", "critique", "compose"}
        if not required.issubset(set(types)):
            return False
    if intent == "forecast":
        if not {"resolve", "retrieve", "analyze", "compose"}.issubset(set(types)):
            return False
    if intent in {"compare", "attribution"}:
        required = {"resolve", "retrieve", "analyze", "critique", "compose"}
        if not required.issubset(set(types)):
            return False
    if intent == "policy" and NAME_RE.search(question) and not is_procedure_question(question):
        return False
    return True


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
) -> dict[str, Any] | None:
    """Return plan dict, unmatched dict, or None when LLM unavailable/invalid."""
    raw = chat_completion(
        messages=[
            {"role": "system", "content": _planner_system_prompt()},
            {"role": "user", "content": _build_user_prompt(question, history=history, intent_hint=intent_hint)},
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
    out: dict[str, Any] = {"intent": intent, "reasoning": reasoning, "plan": plan}
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

    llm = plan_with_llm(question, history=history, intent_hint=intent_hint)
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
