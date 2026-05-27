from __future__ import annotations

import pytest

from src.agent.llm_runner import parse_json_response, agent_llm_enabled


def test_parse_json_response_plain():
    payload = parse_json_response('{"decision":"pass","gaps":[]}')
    assert payload["decision"] == "pass"


def test_parse_json_response_codeblock():
    text = '```json\n{"entities":{"employee":{"工号":"A001"}}}\n```'
    payload = parse_json_response(text)
    assert payload["entities"]["employee"]["工号"] == "A001"


def test_agent_llm_enabled_without_key(monkeypatch):
    from src.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "dashscope_api_key", "", raising=False)
    monkeypatch.setattr(settings, "agent_llm_enabled", True, raising=False)
    assert agent_llm_enabled() is False
