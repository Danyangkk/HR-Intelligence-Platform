#!/usr/bin/env python3
"""Tiny project manager for SDD V7_2.

This script intentionally uses only the Python standard library so students can
inspect and run it without installing dependencies.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "Projects_Repo"
REGISTRY_PATH = ROOT / "project-registry.json"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def default_registry() -> dict:
    return {
        "version": 1,
        "projects_root": "Projects_Repo",
        "active_project_id": None,
        "projects": [],
    }


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return default_registry()
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry.setdefault("version", 1)
    registry.setdefault("projects_root", "Projects_Repo")
    registry.setdefault("active_project_id", None)
    registry.setdefault("projects", [])
    return registry


def save_registry(registry: dict) -> None:
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_project(registry: dict, project_id: str) -> dict | None:
    return next((p for p in registry.get("projects", []) if p["id"] == project_id), None)


def ensure_project_dirs(project_dir: Path) -> None:
    for rel in [
        ".sdd",
        ".sdd/test-reports",
        ".sdd/bug_fix",
        ".sdd/tmp",
        "docs",
        "docs/prototypes",
        "docs/澄清文档",
    ]:
        (project_dir / rel).mkdir(parents=True, exist_ok=True)


def copy_harness(project_dir: Path) -> None:
    """Copy project runtime scaffolding.

    Platform adapters (.cursor/.claude/.codex) stay in the Harness root.
    Copying them into every managed project causes rule drift.
    """
    for name in ["pycore"]:
        src = ROOT / name
        dst = project_dir / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def write_project_entrypoints(project_dir: Path) -> None:
    """Write lightweight project-local entrypoints for users who open a project directly."""
    agents = project_dir / "AGENTS.md"
    if not agents.exists():
        agents.write_text(
            """# Managed Project Entry

This project is managed by SDD Harness V7_2.

Recommended workflow: open the Harness root, not this project folder:

```text
../../
```

Core rules live in:

```text
../../harness-core/
```

Project files live here:

```text
.sdd/
docs/
frontend/
backend/
```

Do not create local `.cursor/`, `.claude/`, or `.codex/` rule copies inside this project unless the Harness explicitly asks for it.
""",
            encoding="utf-8",
        )


def init_sdd_files(project_dir: Path, project_id: str, name: str, project_type: str, source: str, repo_url: str | None) -> None:
    ensure_project_dirs(project_dir)

    project_json = project_dir / ".sdd/project.json"
    if not project_json.exists():
        project_json.write_text(
            json.dumps(
                {
                    "id": project_id,
                    "name": name,
                    "project_type": project_type,
                    "source": source,
                    "repo_url": repo_url,
                    "created_at": now(),
                    "last_active": now(),
                    "harness_version": "V7_2",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    status_json = project_dir / ".sdd/status.json"
    if not status_json.exists():
        status_json.write_text(
            json.dumps(
                {
                    "stage": "initialized",
                    "mode": source,
                    "design_ready": False,
                    "development_ready": False,
                    "current_task": None,
                    "blocked": False,
                    "notes": "",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    for filename in ["experience.md", "work-log.md"]:
        dst = project_dir / ".sdd" / filename
        if not dst.exists():
            template = ROOT / "templates/project/.sdd" / filename
            dst.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

    readme = project_dir / "README.md"
    if not readme.exists():
        template = ROOT / "templates/project/README.md"
        readme.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

    write_project_entrypoints(project_dir)


def register_project(project_id: str, name: str, project_type: str, source: str, repo_url: str | None = None, activate: bool = True) -> None:
    registry = load_registry()
    projects = registry.setdefault("projects", [])
    rel_path = f"Projects_Repo/{project_id}"

    existing = get_project(registry, project_id)
    payload = {
        "id": project_id,
        "name": name,
        "path": rel_path,
        "source": source,
        "repo_url": repo_url,
        "project_type": project_type,
        "status": "initialized",
        "created_at": existing.get("created_at") if existing else now(),
        "last_active": now(),
    }

    if existing:
        existing.update(payload)
    else:
        projects.append(payload)

    if activate:
        registry["active_project_id"] = project_id
    save_registry(registry)


def set_active_project(project_id: str) -> dict:
    registry = load_registry()
    project = get_project(registry, project_id)
    if not project:
        raise SystemExit(f"Project not found: {project_id}")

    project_dir = ROOT / project["path"]
    if not (project_dir / ".sdd/project.json").exists():
        raise SystemExit(f"Project is not initialized: {project_dir}")

    registry["active_project_id"] = project_id
    project["last_active"] = now()
    save_registry(registry)
    return project


def active_project(registry: dict | None = None) -> dict | None:
    registry = registry or load_registry()
    active_id = registry.get("active_project_id")
    if not active_id:
        return None
    return get_project(registry, active_id)


def cmd_new(args: argparse.Namespace) -> None:
    project_dir = PROJECTS_ROOT / args.id
    project_dir.mkdir(parents=True, exist_ok=True)
    copy_harness(project_dir)
    init_sdd_files(project_dir, args.id, args.name, args.type, "new", None)
    register_project(args.id, args.name, args.type, "new", activate=True)
    print(f"Project created: {project_dir}")
    print(f"Active project: {args.id}")
    print(f"active_project_path: Projects_Repo/{args.id}/")


def cmd_use(args: argparse.Namespace) -> None:
    project = set_active_project(args.id)
    print(f"Active project: {project['id']}")
    print(f"active_project_path: {project['path']}/")


def cmd_current(_: argparse.Namespace) -> None:
    registry = load_registry()
    project = active_project(registry)
    if not project:
        print("No active project. Use `python scripts/sdd_project.py list` then `python scripts/sdd_project.py use <id>`.")
        return
    print(f"Active project: {project['id']}")
    print(f"Name: {project['name']}")
    print(f"Type: {project['project_type']}")
    print(f"Status: {project['status']}")
    print(f"active_project_path: {project['path']}/")


def cmd_list(_: argparse.Namespace) -> None:
    registry = load_registry()
    active_id = registry.get("active_project_id")
    for project in registry.get("projects", []):
        marker = "*" if project["id"] == active_id else " "
        print(f"{marker} {project['id']}	{project['project_type']}	{project['status']}	{project['path']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SDD V7_2 project manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    new = sub.add_parser("new", help="Create a new managed project and set it active")
    new.add_argument("id", help="project id, e.g. customer-service")
    new.add_argument("--name", required=True, help="human-readable project name")
    new.add_argument("--type", default="unknown", choices=["web", "mobile", "unknown"])
    new.set_defaults(func=cmd_new)

    use = sub.add_parser("use", help="Set active project")
    use.add_argument("id", help="project id")
    use.set_defaults(func=cmd_use)

    current = sub.add_parser("current", help="Show active project")
    current.set_defaults(func=cmd_current)

    list_cmd = sub.add_parser("list", help="List registered projects")
    list_cmd.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
