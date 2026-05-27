#!/usr/bin/env python3
"""Check SDD Harness V7_2 platform adapter consistency."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


FORBIDDEN_PATTERNS = [
    ".output/Plan.md",
    ".output/plan.md",
    ".output/startup.md",
    "继续推进后端开发吗",
    "是否继续推进后端",
    "用户确认满意后进入后端开发",
    "Developer 不允许自行装包",
    "禁止安装依赖（列出需要的依赖命令即可）",
    "scenario-alignment",
    "docs/需求文档",
    "harness-core/skills/scenario-alignment",
    "gpt-5.4",
    "gpt-5.5",
]


REQUIRED_PATHS = [
    ROOT / "AGENTS.md",
    ROOT / ".codex" / "README.md",
    ROOT / ".codex" / "config.toml",
    ROOT / ".codex" / "agents" / "planner.toml",
    ROOT / ".codex" / "agents" / "developer.toml",
    ROOT / ".codex" / "agents" / "tester.toml",
    ROOT / ".codex" / "commands" / "sdd-new-project.md",
    ROOT / ".codex" / "commands" / "sdd-align.md",
    ROOT / ".codex" / "commands" / "sdd-start.md",
    ROOT / ".codex" / "commands" / "sdd-bugfix.md",
    ROOT / "harness-core" / "protocols" / "codex-subagents.md",
    ROOT / "harness-core" / "skills" / "alignment" / "SKILL.md",
    ROOT / "templates" / "project" / "docs" / "澄清文档",
]


FORBIDDEN_PATHS = [
    ROOT / "templates" / "project" / "docs" / "需求文档",
    ROOT / "harness-core" / "skills" / "scenario-alignment",
    ROOT / ".cursor" / "skills" / "scenario-alignment",
]


ADAPTER_DIRS = [
    ROOT / ".cursor",
    ROOT / ".claude",
    ROOT / ".codex",
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def scan_forbidden_patterns() -> list[str]:
    problems: list[str] = []
    scan_roots = [
        ROOT / "AGENTS.md",
        ROOT / "harness-core",
        ROOT / ".cursor",
        ROOT / ".claude",
        ROOT / ".codex",
        ROOT / "scripts",
        ROOT / "templates",
    ]

    for target in scan_roots:
        paths = [target] if target.is_file() else list(target.rglob("*")) if target.exists() else []
        for path in paths:
            if not path.is_file():
                continue
            if path == Path(__file__).resolve():
                continue
            text = read_text(path)
            for pattern in FORBIDDEN_PATTERNS:
                for line_no, line in enumerate(text.splitlines(), start=1):
                    if pattern not in line:
                        continue
                    if "不得" in line or "不要" in line or "禁止" in line:
                        continue
                    problems.append(f"{path.relative_to(ROOT)}:{line_no} contains forbidden pattern: {pattern}")
    return problems


def scan_required_and_forbidden_paths() -> list[str]:
    problems: list[str] = []
    for path in REQUIRED_PATHS:
        if not path.exists():
            problems.append(f"missing required path: {path.relative_to(ROOT)}")
    for path in FORBIDDEN_PATHS:
        if path.exists():
            problems.append(f"forbidden legacy path exists: {path.relative_to(ROOT)}")
    return problems


def scan_dev_standard_references() -> list[str]:
    problems: list[str] = []
    scan_roots = [
        ROOT / "AGENTS.md",
        ROOT / "README.md",
        ROOT / "START.md",
        ROOT / "HARNESS.md",
        ROOT / "harness-core",
        ROOT / ".cursor",
        ROOT / ".claude",
        ROOT / ".codex",
        ROOT / "scripts",
        ROOT / "templates",
    ]

    for target in scan_roots:
        paths = [target] if target.is_file() else list(target.rglob("*")) if target.exists() else []
        for path in paths:
            if not path.is_file() or path == Path(__file__).resolve():
                continue
            text = read_text(path)
            for line_no, line in enumerate(text.splitlines(), start=1):
                if "harness-core/dev-standards/" in line and ".mdc" in line:
                    problems.append(f"{path.relative_to(ROOT)}:{line_no} references core dev-standards .mdc")
    return problems


def scan_project_platform_copies() -> list[str]:
    problems: list[str] = []
    projects_root = ROOT / "Projects_Repo"
    if not projects_root.exists():
        return problems

    for project in projects_root.iterdir():
        if not project.is_dir():
            continue
        for name in [".cursor", ".claude", ".codex"]:
            if (project / name).exists():
                problems.append(f"{project.relative_to(ROOT)} contains platform adapter copy: {name}")
    return problems


def scan_adapter_core_leakage() -> list[str]:
    problems: list[str] = []
    allowed_phrases = [
        "harness-core/",
        "SDD Harness",
        "适配器",
        "adapter",
    ]

    for adapter_dir in ADAPTER_DIRS:
        if not adapter_dir.exists():
            problems.append(f"missing adapter dir: {adapter_dir.relative_to(ROOT)}")
            continue
        for path in adapter_dir.rglob("*"):
            if not path.is_file():
                continue
            text = read_text(path)
            if path.suffix in {".md", ".mdc", ".toml"} and "harness-core/" not in text and path.name != "config.toml":
                if not any(phrase in text for phrase in allowed_phrases):
                    problems.append(f"{path.relative_to(ROOT)} may not reference harness-core")
    return problems


def main() -> int:
    problems = []
    problems.extend(scan_forbidden_patterns())
    problems.extend(scan_required_and_forbidden_paths())
    problems.extend(scan_dev_standard_references())
    problems.extend(scan_project_platform_copies())
    problems.extend(scan_adapter_core_leakage())

    if problems:
        print("FAIL: SDD Harness consistency problems found")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("PASS: SDD Harness consistency checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
