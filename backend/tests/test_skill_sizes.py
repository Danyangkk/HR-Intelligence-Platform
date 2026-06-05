"""Skill volume gate — full bodies must stay within tier-2 per-skill budget."""

from __future__ import annotations

from pathlib import Path

_SKILLS_ROOT = Path(__file__).resolve().parents[1] / "src" / "agent" / "skills"
_MAX_BODY_CHARS = 6000


def _skill_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4 :].strip()
    return text.strip()


def test_each_skill_body_within_budget():
    paths = sorted(_SKILLS_ROOT.glob("*/SKILL.md"))
    assert paths, "no SKILL.md files found"
    oversize: list[str] = []
    for path in paths:
        body = _skill_body(path)
        if len(body) > _MAX_BODY_CHARS:
            oversize.append(f"{path.parent.name}: {len(body)} chars")
    assert not oversize, "SKILL.md bodies exceed 6000 chars:\n" + "\n".join(oversize)
