from __future__ import annotations

from src.agent.resolver import EmployeeLookupResult


def test_employee_lookup_clarify_payload():
    result = EmployeeLookupResult(
        kind="ambiguous",
        candidates=[
            {"姓名": "王伟", "工号": "A0210", "事业部": "杭综部门", "部门": "渠道组"},
            {"姓名": "王伟", "工号": "A0455", "事业部": "职能部门", "部门": "财务"},
        ],
    )
    clarify = result.clarify_payload("王伟")
    assert clarify["kind"] == "employee"
    assert "2 位" in clarify["question"]
    assert len(clarify["options"]) == 2
    assert "A0210" in clarify["options"][0]["label"]
