from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.clarify_helpers import build_employee_clarify
from src.agent.tools.registry import invoke_tool

ROSTER_L3 = "l3-2-1-4"


@dataclass
class EmployeeLookupResult:
    kind: Literal["found", "not_found", "ambiguous"]
    employee: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] | None = None

    def clarify_payload(self, name: str) -> dict[str, Any]:
        if self.kind == "ambiguous" and self.candidates:
            return build_employee_clarify(name, self.candidates)
        return {
            "kind": "employee",
            "question": f"系统中未找到「{name}」，请确认姓名是否正确。",
            "options": [],
        }


def _employee_from_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "姓名": item.get("姓名"),
        "工号": item.get("工号"),
        "部门": item.get("部门"),
        "事业部": item.get("事业部") or item.get("公司"),
    }


def _lookup_clarify(
    ctx,
    *,
    clarify: dict[str, Any],
    entities: dict[str, Any],
    summary: str,
) -> dict[str, Any]:
    return {
        **ctx.to_state_patch(),
        "clarify": clarify,
        "entities": entities,
        "trace": [ctx.trace_entry(subtask_id="resolver", summary=summary)],
    }


def _lookup_success(
    ctx,
    *,
    entities: dict[str, Any],
    summary: str,
) -> dict[str, Any]:
    return {
        **ctx.to_state_patch(),
        "entities": entities,
        "trace": [ctx.trace_entry(subtask_id="resolver", summary=summary)],
    }


async def _lookup_employee(db: AsyncSession, name: str) -> EmployeeLookupResult:
    result = await invoke_tool(
        "query_structured",
        db,
        l3_id=ROSTER_L3,
        filters={"姓名": name},
        page_size=20,
        role="agent",
    )
    matches = [_employee_from_item(item) for item in (result.get("items") or []) if str(item.get("姓名") or "") == name]
    if not matches:
        return EmployeeLookupResult(kind="not_found")
    if len(matches) == 1:
        return EmployeeLookupResult(kind="found", employee=matches[0])
    return EmployeeLookupResult(kind="ambiguous", candidates=matches)


def _extract_month(question: str) -> str | None:
    m = re.search(r"(\d{1,2})\s*月", question)
    if not m:
        return None
    month = int(m.group(1))
    year_m = re.search(r"(20\d{2})\s*年", question)
    year = int(year_m.group(1)) if year_m else 2025
    return f"{year:04d}-{month:02d}"
