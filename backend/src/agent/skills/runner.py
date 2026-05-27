"""Runtime skill loader — agents execute SOP steps from SKILL.md at run time."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.agent.skills.loader import SKILL_DISPLAY, skills_for_agent
from src.agent.state import AgentState

_STEP_RE = re.compile(r"^(\d+)\.\s*(.+)$")


@dataclass
class SkillRunContext:
    agent: str
    skills: list[dict[str, Any]]
    sop_executed: list[dict[str, Any]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)

    def run_step(self, skill_id: str, step_no: int, summary: str | None = None) -> None:
        skill = next((s for s in self.skills if s["id"] == skill_id), None)
        label = skill["name"] if skill else SKILL_DISPLAY.get(skill_id, skill_id)
        text = summary or _step_text(skill, step_no) or f"步骤 {step_no}"
        self.sop_executed.append(
            {
                "skill_id": skill_id,
                "skill": label,
                "step": step_no,
                "summary": text,
            }
        )

    def record_tool(self, tool_name: str) -> None:
        if tool_name not in self.tools_used:
            self.tools_used.append(tool_name)

    def skill_label(self) -> str:
        names = [s["name"] for s in self.skills[:2]]
        return " · ".join(names) if names else self.agent

    def to_state_patch(self, *, include_active_skills: bool = True) -> dict[str, Any]:
        patch: dict[str, Any] = {"sop_executed": list(self.sop_executed)}
        if include_active_skills:
            patch["active_skills"] = [{"id": s["id"], "name": s["name"]} for s in self.skills]
        return patch

    def trace_entry(self, *, subtask_id: str, summary: str, agent: str | None = None) -> dict[str, Any]:
        return {
            "subtask_id": subtask_id,
            "agent": agent or self.agent,
            "skill": self.skill_label(),
            "sop": list(self.sop_executed),
            "tools": list(self.tools_used),
            "summary": summary,
        }


def begin_agent_run(
    agent: str,
    state: AgentState,
    *,
    subtask_type: str | None = None,
) -> SkillRunContext:
    intent = state.get("intent")
    skills = skills_for_agent(agent, intent=str(intent) if intent else None, subtask_type=subtask_type)
    return SkillRunContext(agent=agent, skills=skills)


def _step_text(skill: dict[str, Any] | None, step_no: int) -> str | None:
    if not skill:
        return None
    in_sop = False
    for line in (skill.get("content") or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("## SOP"):
            in_sop = True
            continue
        if in_sop and stripped.startswith("##"):
            break
        if not in_sop:
            continue
        match = _STEP_RE.match(stripped)
        if match and int(match.group(1)) == step_no:
            return match.group(2).strip()
    return None
