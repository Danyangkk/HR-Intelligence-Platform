"""Eval case YAML draft helpers — read-only; eval_set.yaml is edited via Git only."""

from __future__ import annotations

import re
from typing import Any

from src.eval.loader import load_eval_set
from src.eval.set_version import get_eval_set_version

_INTENT_HINTS: list[tuple[str, str]] = [
    ("aggregate", "aggregate"),
    ("聚合", "aggregate"),
    ("policy", "policy"),
    ("制度", "policy"),
    ("lookup", "lookup"),
    ("查询", "lookup"),
    ("list", "list"),
    ("列表", "list"),
    ("compare", "compare"),
    ("对比", "compare"),
    ("attribution", "attribution"),
    ("归因", "attribution"),
    ("chitchat", "chitchat"),
    ("闲聊", "chitchat"),
]

_MEANINGFUL_EXPECTED_KEYS = frozenset(
    {
        "reject",
        "chitchat",
        "reply_contains",
        "expected_modules",
        "expected_doc_chunks",
        "answer_points",
        "expected_citations",
        "forbid",
        "forbid_path",
        "metric_callouts",
        "must_load_skills",
        "clarify_or_inherit",
    }
)

_PLACEHOLDER_INTENTS = frozenset({"", "todo", "tbd", "placeholder", "待补"})


def is_stub_eval_case(case: dict[str, Any]) -> bool:
    """True when expected is empty or only contains placeholder intent."""
    expected = case.get("expected") or {}
    if not expected:
        return True
    if any(k in expected for k in _MEANINGFUL_EXPECTED_KEYS):
        return False
    intent = str(expected.get("intent") or "").strip().lower()
    return intent in _PLACEHOLDER_INTENTS


def find_stub_eval_case_ids(path=None) -> list[str]:
    return [c["id"] for c in load_eval_set(path) if is_stub_eval_case(c)]


def list_eval_case_ids() -> dict[str, Any]:
    cases = load_eval_set()
    return {
        "ids": [c["id"] for c in cases],
        "version": get_eval_set_version(),
    }


def _infer_intent_from_hint(hint: str) -> str | None:
    text = (hint or "").lower()
    for token, intent in _INTENT_HINTS:
        if token in text:
            return intent
    return None


def _extract_quoted_query(hint: str) -> str | None:
    for pattern in (r"[「『\"']([^」』\"']+)[」』\"']", r"加['\"]([^'\"]+)['\"]"):
        match = re.search(pattern, hint or "")
        if match:
            return match.group(1).strip()
    return None


def _default_layers(intent: str | None) -> list[int]:
    if intent == "policy":
        return [1, 2, 3]
    return [1]


def _is_guardrail_scenario(*parts: str | None) -> bool:
    blob = " ".join(p for p in parts if p).lower()
    return "guardrail" in blob or ("拦截" in blob and ("aggregate" in blob or "成本" in blob))


def build_eval_case_yaml_draft(
    *,
    ticket_id: int,
    draft_changes: dict[str, Any] | None,
    test_requirement: str | None,
    content_biz: str | None,
    source_phenomenon: str | None = None,
) -> str:
    """Build a read-only YAML stub for manual append to eval_set.yaml."""
    draft = draft_changes or {}
    hint = str(draft.get("add_test_case") or test_requirement or "").strip()
    query = (
        _extract_quoted_query(hint)
        or _extract_quoted_query(content_biz or "")
        or (source_phenomenon or "").strip()
        or (content_biz or "").strip()
        or "TODO: 填写评测 query"
    )
    intent = _infer_intent_from_hint(hint)
    guardrail = _is_guardrail_scenario(hint, content_biz, source_phenomenon)
    if guardrail and not intent:
        intent = "aggregate"
    case_id = f"e-tkt-{ticket_id:03d}-1"
    layers = _default_layers(intent)
    layer_text = ", ".join(str(x) for x in layers)

    lines = [
        f"- id: {case_id}",
        f'  query: "{query.replace(chr(34), chr(92) + chr(34))}"',
        f"  layer: [{layer_text}]",
        "  expected: {}",
    ]
    if guardrail:
        lines.extend(
            [
                "  # guardrail 场景：aggregate 提问被薪资 guardrail 拦截",
                "  # 建议 expected.reject: true（或 rejected: true）",
            ]
        )
    else:
        lines.append("  # TODO: 补全 intent / reject / answer_points 等断言后入集")
        if intent:
            lines.append(f"  # 建议 intent: {intent}")
    return "\n".join(lines)
